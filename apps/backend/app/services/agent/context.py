"""上下文装配：AgentMessage → OpenAI wire + 轮组原子截断 + pinned 预算闭合。

截断以「轮组」为原子单位（UserMessage 起组，到下一个 UserMessage 前），
从最旧开始整组丢弃 —— tool 结果永不离开其 assistant(tool_calls) 父消息
（OpenAI 协议要求 tool 消息闭合其父调用）。
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence

from app.core.errors import BusinessError

from app.services.agent.types import AgentMessage, AssistantMessage, ToolResultMessage, UserMessage

TOOL_RESULT_MARK = '\n…[工具结果已截断]'
OUTPUT_RESERVE_CHARS = 12_000
_SURROGATE = re.compile('[\ud800-\udfff]')


def wire_arguments(arguments: dict) -> str:
    """参数对象 → 请求体里的 function.arguments 文本（pi wire 上的 JSON.stringify）。

    参数在 AI 层已解析成对象（provider 用 json_repair 的阶梯，绝不抛错），
    因此这里只是序列化，不存在"传出非法 JSON"的可能。
    """
    return json.dumps(arguments, ensure_ascii=False)


def sanitize_text(text: str) -> str:
    """清洗孤立代理项（pi sanitizeSurrogates / replaceUnpairedSurrogates 同目的）。

    Python 字符串里出现 U+D800-U+DFFF 一定是解码残留（正常 astral 字符是单个码点），
    序列化进请求体会产生非法 UTF-8 → 上游 400 或乱码。统一替换为 U+FFFD。
    """
    return _SURROGATE.sub('\ufffd', text) if _SURROGATE.search(text) else text


def to_wire(system: str, messages: Sequence[AgentMessage]) -> list[dict]:
    wire: list[dict] = [{'role': 'system', 'content': sanitize_text(system)}] if system else []
    for message in messages:
        if isinstance(message, UserMessage):
            wire.append({'role': 'user', 'content': sanitize_text(message.text)})
        elif isinstance(message, AssistantMessage):
            entry: dict = {'role': 'assistant', 'content': sanitize_text(message.content)}
            if message.tool_calls:
                entry['tool_calls'] = [
                    {'id': call.call_id, 'type': 'function',
                     'function': {'name': call.name,
                                  'arguments': sanitize_text(wire_arguments(call.arguments))}}
                    for call in message.tool_calls
                ]
            wire.append(entry)
        else:
            wire.append({'role': 'tool', 'tool_call_id': message.call_id,
                         'content': sanitize_text(message.content)})
    return wire


def message_chars(message: AgentMessage) -> int:
    """单条消息的 wire 占用（上下文预算的唯一口径）。

    assistant 计 content + tool_calls（参数按序列化后的长度计，与请求体一致）；
    reasoning 不发回模型（pi thinking 不进上下文），不计入预算。
    context 的截断判定与 compaction 的触发/保留估算共用这一份实现。
    """
    if isinstance(message, AssistantMessage):
        return len(message.content) + sum(
            len(call.name) + len(wire_arguments(call.arguments)) for call in message.tool_calls)
    if isinstance(message, UserMessage):
        return len(message.text)
    return len(message.content)


def _chars(messages: Sequence[AgentMessage]) -> int:
    return sum(message_chars(message) for message in messages)


def groups(messages: Sequence[AgentMessage]) -> list[list[AgentMessage]]:
    """对话按轮组切分（UserMessage 起组，到下一 UserMessage 前；供截断与 compaction 使用）。"""
    result: list[list[AgentMessage]] = []
    current: list[AgentMessage] = []
    for message in messages:
        if isinstance(message, UserMessage) and current:
            result.append(current)
            current = []
        current.append(message)
    if current:
        result.append(current)
    return result


def assemble(system: str, messages: Sequence[AgentMessage], *,
             max_chars: int = 180_000, max_tool_result_chars: int = 24_000,
             tools_wire_chars: int = 0) -> tuple[list[dict], bool]:
    """返回 (wire, truncated)。当前轮组永不丢弃；pinned 消息（read_skill 等指令性
    内容）既免单项截断也不随轮组丢弃；不可截断部分超限抛 context_overflow。

    预算闭合：system + 工具定义 + pinned 总量 + 当前输入 + 输出预留
    必须放得下，放不下时显式失败（带各分项占用）而不是等上游 400。
    floor 对 pinned 只计一次：当前轮组内的 pinned 计入当前输入，历史轮组
    的计入 pinned 总量，二者不重叠。
    """
    capped: list[AgentMessage] = []
    truncated = False
    for message in messages:
        if (isinstance(message, ToolResultMessage) and not message.pinned
                and len(message.content) > max_tool_result_chars):
            capped.append(ToolResultMessage(message.call_id, message.name,
                                            message.content[:max_tool_result_chars] + TOOL_RESULT_MARK,
                                            message.is_error))
            truncated = True
        else:
            capped.append(message)

    all_groups = groups(capped)
    current = all_groups[-1] if all_groups else []
    # floor 对 pinned 只计一次：当前轮组的 pinned 已含在 _chars(current) 内，
    # 这里只累计历史轮组的 pinned（其永不随轮组丢弃，必须全额预留）。
    pinned_total = sum(len(m.content) for group in all_groups[:-1] for m in group
                       if isinstance(m, ToolResultMessage) and m.pinned)
    floor = len(system) + tools_wire_chars + pinned_total + OUTPUT_RESERVE_CHARS + _chars(current)
    if all_groups and floor > max_chars:
        raise BusinessError(
            20009,
            f'上下文超出预算（{max_chars} 字符）：system {len(system)} + 工具定义 {tools_wire_chars}'
            f' + 常驻内容 {pinned_total} + 当前输入 {_chars(current)} + 输出预留 {OUTPUT_RESERVE_CHARS}',
        )
    budget = max_chars - floor
    kept: list[list[AgentMessage]] = [current] if all_groups else []
    used = 0
    for group in reversed(all_groups[:-1]):
        if any(isinstance(m, ToolResultMessage) and m.pinned for m in group):
            # pinned 豁免（types.ToolResultMessage 契约）：指令性内容永不随轮组
            # 丢弃；其占用已由 floor 预留（max_pinned_chars 在装载时已封顶）。
            kept.insert(0, group)
            continue
        size = _chars(group)
        if used + size > budget:
            truncated = True
            break  # 更旧的轮组一并丢弃
        kept.insert(0, group)
        used += size
    trimmed = [message for group in kept for message in group]
    return to_wire(system, trimmed), truncated
