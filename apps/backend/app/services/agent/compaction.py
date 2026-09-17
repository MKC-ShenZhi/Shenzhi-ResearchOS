"""LLM 上下文压缩：pi packages/agent harness/compaction 的语义移植。

对照 pi 源码逐项对齐（compaction.ts + compaction/utils.ts）：
- 触发条件：优先用 provider 报告的真实用量（挂最终 assistant 消息，token×4
  折回字符预算），其后消息按字符估算；无用量回退全量字符估算
  （estimateContextTokens 的字符版，预算单位与 context.assemble 一致）。
- 保留近期：按 keep_recent_chars 从最新往回保留完整轮组原文
  （keepRecentTokens 的字符版；轮组边界天然是 pi 的合法 cut point——
  user 起组、tool 结果永不离开其 assistant 父，因此无需 pi 的 split-turn 处理）。
- 结构化摘要：Goal / Constraints & Preferences / Progress / Key Decisions /
  Next Steps / Critical Context 固定模板（SUMMARIZATION_PROMPT 移植）。
- 迭代摘要：已有摘要走 UPDATE 路径（previousSummary + UPDATE_SUMMARIZATION_PROMPT），
  保留旧信息、合并新进展，摘要不会被再摘要；跨 run 的旧摘要从历史消息中恢复。
- 文件操作清单：read_file/write_file/edit_file 调用聚合为 <read-files> /
  <modified-files> 追加到摘要尾部（extractFileOpsFromMessage + formatFileOperations），
  跨 compaction 累积并随 Checkpoint 持久化。
- 序列化：[User] / [Assistant] / [Assistant tool calls] / [Tool result]
  （单条工具结果截 2k，serializeConversation 同款）。

本基座扩展（pi 无此概念）：pinned 轮组（read_skill 指令）整组永不折叠。
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from contextlib import aclosing
from dataclasses import dataclass

from app.services.agent.context import groups, message_chars
from app.services.agent.provider import ModelProvider, ModelRequest, TextDelta
from app.services.agent.types import AgentMessage, AssistantMessage, ToolResultMessage, UserMessage

logger = logging.getLogger('app.agent')

TOOL_RESULT_MAX_CHARS = 6_000
MAX_SUMMARY_CHARS = 12_000
CHARS_PER_TOKEN = 4  # pi estimateTokens 的 chars/4 启发式逆向：token 用量折回字符预算

SUMMARIZATION_SYSTEM_PROMPT = (
    'You are a context summarization assistant. Your task is to read a conversation '
    'between a user and an AI assistant, then produce a structured summary following '
    'the exact format specified.\n\n'
    'Do NOT continue the conversation. Do NOT respond to any questions in the '
    'conversation. ONLY output the structured summary.'
)

SUMMARIZATION_PROMPT = '''The messages above are a conversation to summarize. Create a structured context checkpoint summary that another LLM will use to continue the work.

Use this EXACT format:

## Goal
[What is the user trying to accomplish? Can be multiple items if the session covers different tasks.]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next]

## Critical Context
- [Any data, examples, or references needed to continue]
- [Or "(none)" if not applicable]

Keep each section concise. Preserve exact file paths, function names, and error messages.'''

UPDATE_SUMMARIZATION_PROMPT = '''The messages above are NEW conversation messages to incorporate into the existing summary provided in <previous-summary> tags.

Update the existing structured summary with new information. RULES:
- PRESERVE all existing information from the previous summary
- ADD new progress, decisions, and context from the new messages
- UPDATE the Progress section: move items from "In Progress" to "Done" when completed
- UPDATE "Next Steps" based on what was accomplished
- PRESERVE exact file paths, function names, and error messages
- If something is no longer relevant, you may remove it

Use this EXACT format:

## Goal
[Preserve existing goals, add new ones if the task expanded]

## Constraints & Preferences
- [Preserve existing, add new ones discovered]

## Progress
### Done
- [x] [Include previously done items AND newly completed items]

### In Progress
- [ ] [Current work - update based on progress]

### Blocked
- [Current blockers - remove if resolved]

## Key Decisions
- **[Decision]**: [Brief rationale] (preserve all previous, add new)

## Next Steps
1. [Update based on current state]

## Critical Context
- [Preserve important context, add new if needed]

Keep each section concise. Preserve exact file paths, function names, and error messages.'''

# 工具名 → 文件操作类别（pi utils.ts 的 read/write/edit 映射，对应我们的工作区工具）
_FILE_TOOL_KINDS = {'read_file': 'read', 'write_file': 'written', 'edit_file': 'edited'}

_SUMMARY_OPEN = '<context_summary>\n以下是更早对话的要点摘要（原文已压缩）：\n\n'
_SUMMARY_CLOSE = '\n</context_summary>'


def wrap_summary(summary: str) -> str:
    return _SUMMARY_OPEN + summary + _SUMMARY_CLOSE


def unwrap_summary(text: str) -> str:
    """从 <context_summary> 包裹消息中取出摘要正文（跨 run 恢复 previousSummary 用）。"""
    if text.startswith(_SUMMARY_OPEN) and text.endswith(_SUMMARY_CLOSE):
        return text[len(_SUMMARY_OPEN):len(text) - len(_SUMMARY_CLOSE)]
    return text


def estimate_context_chars(messages: Sequence[AgentMessage], *,
                           system_chars: int = 0, tools_wire_chars: int = 0) -> int:
    """pi estimateContextTokens 的字符版：优先最近 assistant 的真实用量
    （usage_tokens×4），其后消息按字符估算；无用量时全量字符估算。"""
    usage_index = -1
    usage_tokens = 0
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, AssistantMessage) and message.usage_tokens > 0:
            usage_index = index
            usage_tokens = message.usage_tokens
            break
    if usage_index < 0:
        estimated = sum(message_chars(m) for m in messages)
    else:
        trailing = sum(message_chars(m) for m in messages[usage_index + 1:])
        estimated = usage_tokens * CHARS_PER_TOKEN + trailing
    return system_chars + tools_wire_chars + estimated


def _truncate_for_summary(text: str, max_chars: int = TOOL_RESULT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return f'{text[:max_chars]}\n\n[... {len(text) - max_chars} more characters truncated]'


def serialize_conversation(messages: Iterable[AgentMessage]) -> str:
    """AgentMessage → 摘要用纯文本（pi serializeConversation 移植）。"""
    parts: list[str] = []
    for message in messages:
        if isinstance(message, AssistantMessage):
            if message.reasoning:
                parts.append(f'[Assistant thinking]: {message.reasoning}')
            if message.content:
                parts.append(f'[Assistant]: {message.content}')
            if message.tool_calls:
                rendered = []
                for call in message.tool_calls:
                    args_str = ', '.join(
                        f'{key}={json.dumps(value, ensure_ascii=False, default=str)}'
                        for key, value in call.arguments.items())
                    rendered.append(f'{call.name}({args_str})')
                parts.append(f'[Assistant tool calls]: {"; ".join(rendered)}')
        elif isinstance(message, ToolResultMessage):
            if message.content:
                parts.append(f'[Tool result]: {_truncate_for_summary(message.content)}')
        elif message.text:
            parts.append(f'[User]: {message.text}')
    return '\n\n'.join(parts)


def extract_file_ops(messages: Iterable[AgentMessage], *,
                     prior_read: Sequence[str] = (), prior_modified: Sequence[str] = (),
                     ) -> tuple[set[str], set[str]]:
    """聚合 assistant 工具调用中的读/写文件集合，并与上次 compaction 清单合并
    （pi extractFileOps + CompactionDetails 续传）。"""
    read = set(prior_read)
    modified = set(prior_modified)
    for message in messages:
        if not isinstance(message, AssistantMessage):
            continue
        for call in message.tool_calls:
            if call.name not in _FILE_TOOL_KINDS:
                continue
            path = call.arguments.get('path')
            if not isinstance(path, str) or not path:
                continue
            if _FILE_TOOL_KINDS[call.name] == 'read':
                read.add(path)
            else:
                modified.add(path)
    return read, modified


def format_file_operations(read_files: Sequence[str], modified_files: Sequence[str]) -> str:
    """文件清单格式化为摘要尾部元数据（pi formatFileOperations 同款标签）。"""
    sections = []
    if read_files:
        sections.append('<read-files>\n' + '\n'.join(read_files) + '\n</read-files>')
    if modified_files:
        sections.append('<modified-files>\n' + '\n'.join(modified_files) + '\n</modified-files>')
    if not sections:
        return ''
    return '\n\n' + '\n\n'.join(sections)


@dataclass
class CompactionPlan:
    """压缩切分结果（纯数据）：折叠范围、保留原文、文件清单。"""
    fold_messages: list[AgentMessage]
    retained: list[AgentMessage]
    chars_before: int
    read_files: list[str]
    modified_files: list[str]


def plan_compaction(messages: Sequence[AgentMessage], *, keep_recent_chars: int,
                    prior_read: Sequence[str] = (), prior_modified: Sequence[str] = (),
                    system_chars: int = 0, tools_wire_chars: int = 0) -> CompactionPlan | None:
    """pi prepareCompaction/findCutPoint 的轮组版：从最新往回按预算保留整组原文，
    其余为折叠范围；pinned 轮组永不折叠（整组保留，tool 结果不离其父）。"""
    all_groups = groups(list(messages))
    if len(all_groups) < 2:
        return None
    kept: list[list[AgentMessage]] = [all_groups[-1]]
    used = sum(message_chars(m) for m in all_groups[-1])
    exhausted = False
    for group in reversed(all_groups[:-1]):
        if any(isinstance(m, ToolResultMessage) and m.pinned for m in group):
            kept.insert(0, group)  # 指令性内容整组豁免，不消耗保留预算
            continue
        if exhausted or used >= keep_recent_chars:
            exhausted = True  # 非指令内容到此为止，更旧的组全部折叠
            continue
        kept.insert(0, group)
        used += sum(message_chars(m) for m in group)
    # kept 可能不连续（pinned 组插队保留），fold 按补集计算而非位置切片
    kept_ids = {id(group) for group in kept}
    fold = [m for group in all_groups if id(group) not in kept_ids for m in group]
    if not fold:
        return None
    read, modified = extract_file_ops(fold, prior_read=prior_read, prior_modified=prior_modified)
    read_only = sorted(path for path in read if path not in modified)
    return CompactionPlan(
        fold_messages=fold,
        retained=[m for group in kept for m in group],
        chars_before=estimate_context_chars(messages, system_chars=system_chars,
                                            tools_wire_chars=tools_wire_chars),
        read_files=read_only,
        modified_files=sorted(modified))


async def summarize(provider: ModelProvider, model: str, messages: Sequence[AgentMessage], *,
                    previous_summary: str = '', max_summary_tokens: int = 3072) -> str | None:
    """生成（或迭代更新）结构化摘要；失败返回 None 由调用方跳过本次压缩（pi SummaryRequest）。"""
    conversation = serialize_conversation(messages)
    if not conversation.strip():
        return None
    prompt_text = f'<conversation>\n{conversation}\n</conversation>\n\n'
    if previous_summary:
        prompt_text += f'<previous-summary>\n{previous_summary}\n</previous-summary>\n\n'
    prompt_text += UPDATE_SUMMARIZATION_PROMPT if previous_summary else SUMMARIZATION_PROMPT
    request = ModelRequest(
        model,
        [{'role': 'system', 'content': SUMMARIZATION_SYSTEM_PROMPT},
         {'role': 'user', 'content': prompt_text}],
        [], None, max_summary_tokens)
    try:
        pieces: list[str] = []
        async with aclosing(provider.stream(request)) as stream:
            async for event in stream:
                if isinstance(event, TextDelta):
                    pieces.append(event.text)
        return ''.join(pieces).strip()[:MAX_SUMMARY_CHARS] or None
    except Exception:
        logger.exception('agent.compaction.summarize failed')
        return None


def split_off_summary(messages: Sequence[AgentMessage]) -> tuple[list[AgentMessage], str]:
    """折叠范围若以旧摘要消息开头，剥离并返回其正文（previousSummary 迭代通道，
    使旧摘要不被重复序列化进新摘要）。"""
    if messages and isinstance(messages[0], UserMessage) and messages[0].text.startswith('<context_summary>'):
        return list(messages[1:]), unwrap_summary(messages[0].text)
    return list(messages), ''
