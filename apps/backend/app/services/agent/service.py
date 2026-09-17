"""Agent 运行的应用层组装：runtime 构造、history/附件解析、事件流桥接。

本模块是**组合根**：允许引用基座之外的既有 service（web_search、document_parser、
sessions.repository），基座核心（types/tools/provider/context/runtime/compaction）零依赖；
产品策略（身份/准则/预算）在 policies.py，技能与工作区能力在 skills.py / workspace.py。
API 层只认 service.*，工作区的目录注册与产物访问在这里转出（见文件末尾导出段）。
"""
from __future__ import annotations

import asyncio

from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

from app.core.errors import BusinessError
from app.services.agent import AgentEvent, AgentRuntime, default_store
from app.services.agent.chart_tools import chart_tool, image_search_tool
from app.services.agent.fetch_url import fetch_url_tool
from app.services.agent.knowledge_tools import knowledge_tools
from app.services.agent.policies import (
    IDENTITY, RUN_DEADLINE_S, compose_agent_system, run_deadline_s,
)
from app.services.agent.read_paper import read_paper_tool
from app.services.agent.prompt_templates import (
    find_template, format_template_invocation, prompt_templates,
)
from app.services.agent.types import RUN_START, RunChannel
from app.services.agent.skills import SkillStore, sync_loaded_skill_scripts
from app.services.agent.tools import Tool, ToolSpec, tool
from app.services.agent.types import AgentMessage, RunResult, StopReason, message_from_dict
from app.services.agent.workspace import (
    Workspace, build_workspace_tools, create_workspace, ensure_session_workspace,
    mount_workspace, mount_workspace_into, read_session_file, write_workspace_file,
)
from app.services.document_parser import attachment_context
from app.services.knowledge import KnowledgeService
from app.services.model_provider import TEMPERATURE
from app.services.sessions import repository
from app.services.web_search import web_search

# API 层的调用面（app/api/agent.py 经 service.* 使用）；其余 workspace 符号本模块自用。
# 策略常量与 compose_agent_system 自 policies.py 转出（既有调用方无需改 import）。
__all__ = [
    'build_run_runtime', 'create_workspace', 'decode_history', 'default_store',
    'expand_template_prompt', 'load_templates', 'read_session_file', 'resolve_attachments',
    'run_deadline_s', 'run_events', 'steer_run', 'write_workspace_file',
    'RUN_DEADLINE_S', 'compose_agent_system',
]

PROJECT_CONTEXT_FILES = ('AGENTS.md', 'CLAUDE.md')  # pi contextFiles/AGENTS.md 机制
MAX_PROJECT_CONTEXT_CHARS = 60_000


def load_project_context(root: Path) -> str:
    """工作区根下的项目指令文件 → <project_context> 段（pi buildSystemPrompt 的
    contextFiles 同款包裹格式）。多个文件按固定顺序拼接；单个超限截断。"""
    sections = []
    for name in PROJECT_CONTEXT_FILES:
        target = root / name
        if not target.is_file():
            continue
        content = target.read_text(encoding='utf-8', errors='replace')[:MAX_PROJECT_CONTEXT_CHARS]
        sections.append(f'<project_instructions path="{name}">\n{content}\n</project_instructions>')
    if not sections:
        return ''
    return ('<project_context>\n\nProject-specific instructions and guidelines:\n\n'
            + '\n\n'.join(sections) + '\n</project_context>')


def default_runtime(system: str | Callable[[Sequence[ToolSpec]], str] = compose_agent_system,
                    *, skills: SkillStore | None = None, **overrides: Any) -> AgentRuntime:
    """默认 runtime：工具清单由注册表动态生成（system 工厂）；skills 可注入复用已装载的 store。"""
    return AgentRuntime(skills=skills if skills is not None else default_store(),
                        system=system, **overrides)


def decode_history(raw: Sequence[dict]) -> list[AgentMessage]:
    try:
        return [message_from_dict(item) for item in raw]
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise BusinessError(20001, 'history 消息格式无效') from exc


def resolve_attachments(raw: Sequence[dict], owner: str) -> tuple[str, list[str]]:
    """复用 Chat 的附件管线（uploads 落库 → attachment_context 组装文本）。"""
    from app.schemas.chat import ChatAttachment
    try:
        parsed = [ChatAttachment.model_validate(item) for item in raw]
    except Exception as exc:
        raise BusinessError(20001, 'attachments 格式无效') from exc
    return attachment_context(parsed, owner, repository)


def _web_search_tool() -> Tool:
    from pydantic import BaseModel

    class Args(BaseModel):
        query: str

    import json

    @tool(name='web_search',
          description='联网搜索实时信息（新闻、文档、近期进展、时间敏感事实）。返回标题、URL 与摘要列表；'
                      '学术文献优先用知识库技能。',
          params=Args, timeout_s=90)
    async def search(args: Args) -> str:
        items, warnings = await web_search(args.query)
        if not items:
            raise BusinessError(20004, '；'.join(warnings) or '联网搜索未获得结果')
        return json.dumps([{'title': i['title'], 'url': i['url'], 'snippet': i['snippet']}
                           for i in items], ensure_ascii=False)

    return search


# ---- 工作区：目录注册与产物访问在 workspace.py（pi：文件能力归产品层工具模块），
# service 仅 re-export 供 API 层与既有调用方使用。----
# run 时间预算与系统提示骨架在 policies.py（见文件顶部 import）。


def build_run_runtime(*, owner: str, model: str | None = None, mode: str = 'fast',
                      web_search_on: bool = False, workspace_id: str | None = None,
                      forced_skills: Sequence[str] = (),
                      session_id: str | None = None) -> AgentRuntime:
    """按单次请求组装 runtime：模型/温度 + 可选联网工具 + 可选 Web 工作区 + 强制技能。

    system 的各段落（工具清单/工作区提示/强制技能/挂载说明）按序追加、互不覆盖
    （此前三段各自整段重写，组合请求会互相吞掉）。技能工具从唯一的 store 装载
    （此前 store 仅在 session 分支创建，forced_skills 单独出现会 NameError）。
    """
    overrides: dict[str, Any] = {'temperature': TEMPERATURE.get(mode), 'max_turns': 360,
                                 'deadline_s': run_deadline_s(mode), 'max_context_chars': 360_000,
                                 'compaction': True}
    if model:
        overrides['model'] = model
    store = default_store()
    tools: list[Tool] = []
    sections: list[str] = []
    # 一个 run 只有一个工作区根：会话目录是 agent 的工作台（技能脚本、状态与产物都在
    # 这里）；上传的工作区以内容同步方式挂进来，不再各挂一套同名工具（同名工具会让
    # ToolRegistry 直接构造失败）。无 session 时上传目录自身就是根。
    root: Path | None = None
    hooks: dict[str, Any] = {}
    if session_id or workspace_id:
        root = (ensure_session_workspace(owner, session_id) if session_id
                else mount_workspace(workspace_id, owner).root)
        workspace = Workspace(root)
        tools.extend(build_workspace_tools(workspace))
        mounted = mount_workspace_into(root, workspace_id, owner) if workspace_id else 0
        # 技能脚本随装载到位（渐进披露同样适用于脚本资产）：装载某技能后它的
        # scripts/ 才进工作区，而不是每个请求把整个技能库（实测 1.6MB）搬一遍。
        hooks['after_tool_call'] = sync_loaded_skill_scripts(store, root)
        # 配图工具需要工作区（产物落盘 + 图床路径），因此随工作区挂载：draw_chart 渲图、
        # image_search 缓存原图。未挂工作区时不注册——不宣称做不到的能力。
        tools.append(chart_tool(workspace_root=root, session_id=session_id))
        tools.append(image_search_tool(workspace_root=root, session_id=session_id))
        project_context = load_project_context(root)
        # 通用工作区说明：不点名任何具体业务的文件（研究状态、报告名归技能正文规定）
        sections.append('工作区已就绪（read_file / write_file / edit_file / run_command 可用）。'
                        '中间状态与成果都写成工作区文件，完成后交付并给出文件路径。'
                        '\n技能脚本在装载该技能后同步到 <技能名>/scripts/（在工作区根下执行）。'
                        + (f'\n\n已挂载上传工作区的 {mounted} 个文件到工作区根。' if mounted else '')
                        + (f'\n\n{project_context}' if project_context else ''))
    if forced_skills:
        parts = []
        for name in forced_skills:
            skill = store.get(name)
            if skill is None:
                raise BusinessError(20001, f'技能不存在: {name}')
            parts.append('用户显式选择了技能「' + name + '」，本轮必须遵循：\n\n' + skill.body)
        sections.append('\n\n'.join(parts))
    # 研究取证通道：全文、网页正文、公开检索是"细节论断有据可依"的前提，任何一轮都挂上。
    # 它们自带出网安全网关与降级路径（未配置搜索渠道时返回可读错误，不是崩溃）。
    # 注：web_search 不再由前端开关决定——深研技能的检索路由把它当核心渠道（知识库覆盖不足时升级），
    # 关掉它会让技能正文里的指引变成断链；渠道未配置时工具自身会如实报错。
    tools.append(_web_search_tool())
    tools.append(read_paper_tool(knowledge=KnowledgeService()))
    tools.append(fetch_url_tool())
    # 知识库三件套（paper_search / paper_detail / citation_graph）：与研究取证工具同层，
    # 由基座直接暴露——技能只写"怎么查"，能查什么由基座提供。
    tools.extend(knowledge_tools())

    def agent_system(specs: Sequence[ToolSpec]) -> str:
        return compose_agent_system(specs, extra_sections=tuple(sections))

    return default_runtime(system=agent_system, tools=tools or (), skills=store,
                           ask_user=True,  # 交互式产品：允许 agent 反问用户（见 ask_user.py）
                           **hooks, **overrides)


# ---- 事件流桥接 ----

# 运行中的 steer 通道（run_id → channel）：单进程内 SSE run 的插话入口。
# run 结束（含消费者断开取消）由 worker 的 finally 摘除，绝不泄漏。
_active_channels: dict[str, RunChannel] = {}


def steer_run(run_id: str, text: str) -> bool:
    """向运行中的 run 插话（下一模型请求前注入）；run 不存在返回 False。"""
    channel = _active_channels.get(run_id)
    if channel is None:
        return False
    channel.steer(text)
    return True


def load_templates() -> list[dict]:
    """提示词模板清单（prompts/*.md；目录与缓存归 prompt_templates.py）。"""
    return [{'name': template.name, 'description': template.description,
             'argument_hint': template.argument_hint}
            for template in prompt_templates()]


def expand_template_prompt(prompt: str) -> str:
    """"/tpl <名称> <参数…>" 展开为模板正文（CLI 同语法）；其余原样返回。"""
    if not prompt.startswith('/tpl '):
        return prompt
    parts = prompt[len('/tpl '):].strip().split()
    if not parts:
        return prompt
    template = find_template(parts[0])
    if template is None:
        return prompt
    expanded = format_template_invocation(template, parts[1:])
    return expanded if expanded.strip() else prompt


async def run_events(runtime: AgentRuntime, prompt: str, history: Sequence[AgentMessage] = (),
                     meta: dict | None = None) -> AsyncIterator[tuple[str, dict]]:
    """把 runtime.run 桥接为 (事件名, data) 流；先发 meta（如附件告警），末尾发 result。

    消费方断开时（生成器被关闭）取消运行任务并跳过 result——客户端已不在。
    运行期间持有 RunChannel 并按 run_id 注册，供 steer_run 插话。
    """
    queue: asyncio.Queue = asyncio.Queue()
    box: dict[str, RunResult] = {}
    channel = RunChannel()

    async def worker() -> None:
        def on_event(event: AgentEvent) -> None:
            if event.name == RUN_START:
                _active_channels[event.data['run_id']] = channel
            queue.put_nowait(event)
        try:
            box['result'] = await runtime.run(prompt, history=history,
                                              on_event=on_event, channel=channel)
        finally:
            for key, registered in list(_active_channels.items()):
                if registered is channel:
                    _active_channels.pop(key, None)
            await queue.put(None)

    task = asyncio.create_task(worker())
    try:
        if meta:
            yield ('meta', meta)
        while True:
            event = await queue.get()
            if event is None:
                break
            yield (event.name, {'turn': event.turn, **event.data})
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    result = box.get('result') or RunResult(stop_reason=StopReason.CANCELLED)
    yield ('result', {
        'status': result.status,
        'final_text': result.final_text,
        'output': result.output,
        # 等待用户回答时把问题提到顶层：调用方不必理解 output 的判别联合就能渲染选项
        'question': result.question,
        'turns': result.turns,
        'duration_ms': result.duration_ms,
        'prompt_tokens': result.prompt_tokens,
        'completion_tokens': result.completion_tokens,
        'truncated': result.truncated,
        'error': ({'code': result.error.code, 'message': result.error.message}
                  if result.error else None),
    })
