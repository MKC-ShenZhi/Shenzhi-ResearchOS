"""Assemble an Agent runtime and its product capabilities."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.core.errors import BusinessError
from app.services.agent.execution.runtime import AgentRuntime
from app.integrations.llm.agent_stream import OpenAICompatProvider
from app.integrations.llm.resolver import load_registry
from app.services.agent.extensions.skills import default_store
from app.services.agent.capabilities.chart_tools import chart_tool, image_search_tool
from app.services.agent.capabilities.fetch_url import fetch_url_tool
from app.services.agent.capabilities.knowledge_tools import knowledge_tools
from app.services.agent.app.policies import (
    TEMPERATURE, compose_agent_system, run_deadline_s, tool_call_budget,
)
from app.services.agent.capabilities.read_paper import read_paper_tool
from app.services.agent.capabilities.web_search import web_search_tool
from app.services.agent.extensions.skills import SkillStore, sync_loaded_skill_scripts
from app.services.agent.execution.tools import Tool, ToolSpec, tool
from app.services.agent.execution.types import AgentMessage, message_from_dict
from app.services.agent.extensions.workspace import (
    Workspace, build_workspace_tools, ensure_session_workspace,
    mount_workspace, mount_workspace_into,
)
from app.services.agent.extensions.attachments import attachment_context
from app.services.knowledge.service import KnowledgeService


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
    model = overrides.get('model')
    overrides['model'] = load_registry().resolve_model(
        model, 'agent', require_configured=False).spec.id
    overrides.setdefault('provider', OpenAICompatProvider())
    return AgentRuntime(skills=skills if skills is not None else default_store(),
                        system=system, **overrides)


def decode_history(raw: Sequence[dict]) -> list[AgentMessage]:
    try:
        return [message_from_dict(item) for item in raw]
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise BusinessError(20001, 'history 消息格式无效') from exc


async def resolve_attachments(raw: Sequence[dict], owner: str) -> tuple[str, list[str], dict[str, dict]]:
    """Resolve short-lived parsed Agent uploads and assemble this turn's context."""
    from app.schemas.agent import AgentAttachment
    from app.services.agent_uploads import agent_upload_store
    try:
        parsed = [AgentAttachment.model_validate(item) for item in raw]
    except Exception as exc:
        raise BusinessError(20001, 'attachments 格式无效') from exc
    files = await agent_upload_store.get_many(
        owner, [item.file_id or '' for item in parsed if item.kind == 'file'])
    context, warnings = attachment_context(parsed, files)
    return context, warnings, files


# ---- 工作区：目录注册与产物访问在 workspace.py（pi：文件能力归产品层工具模块），
# service 仅 re-export 供 API 层与既有调用方使用。----
# run 时间预算与系统提示骨架在 policies.py（见文件顶部 import）。


def build_run_runtime(*, owner: str, model: str | None = None, mode: str = 'fast',
                      workspace_id: str | None = None,
                      forced_skills: Sequence[str] = (),
                      session_id: str | None = None,
                      allow_shell: bool = True, runtime_factory: Callable[..., AgentRuntime] = default_runtime) -> AgentRuntime:
    """按单次请求组装 runtime：模型/温度 + 可选联网工具 + 可选 Web 工作区 + 强制技能。

    system 的各段落（工具清单/工作区提示/强制技能/挂载说明）按序追加、互不覆盖
    （此前三段各自整段重写，组合请求会互相吞掉）。技能工具从唯一的 store 装载
    （此前 store 仅在 session 分支创建，forced_skills 单独出现会 NameError）。
    """
    # 预算类参数不用 ×3：上下文预算放大只会把失败点推后并让压缩更晚触发
    # （实测 360k 预算下 20+ 次检索直接溢出）。×3 保留在超时与轮次这类"等得起"的参数上。
    #
    # 但"等得起"也有代价：deadline 90 分钟 + max_tool_calls 无限 = 模型没有收尾压力，
    # 实测一次综述跑 20 分钟以上（read_paper 单次数十秒 × 十几次）。这里给工具调用设预算，
    # 让模型在预算耗尽前必须收敛并交付，而不是无限深挖。
    overrides: dict[str, Any] = {'temperature': TEMPERATURE.get(mode), 'max_turns': 360,
                                 'deadline_s': run_deadline_s(mode), 'max_context_chars': 180_000,
                                 'max_tool_calls': tool_call_budget(mode),
                                 'tool_budget': tool_call_budget(mode),  # 同一个数进系统提示
                                 'compaction': True}
    if model:
        overrides['model'] = model
    fast = (mode == 'fast' and not forced_skills)
    store = SkillStore({}) if fast else default_store()
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
        tools.extend(build_workspace_tools(workspace, allow_shell=allow_shell))
        mounted = mount_workspace_into(root, workspace_id, owner) if workspace_id else 0
        # 技能脚本随装载到位（渐进披露同样适用于脚本资产）：装载某技能后它的
        # scripts/ 才进工作区，而不是每个请求把整个技能库（实测 1.6MB）搬一遍。
        hooks['after_tool_call'] = sync_loaded_skill_scripts(store, root)
        # 配图工具需要工作区（产物落盘 + 图床路径），因此随工作区挂载：draw_chart 渲图、
        # image_search 缓存原图。未挂工作区时不注册——不宣称做不到的能力。
        if not fast:
            tools.append(chart_tool(workspace_root=root, session_id=session_id))
            tools.append(image_search_tool(workspace_root=root, session_id=session_id))
        project_context = load_project_context(root)
        # 通用工作区说明：不点名任何具体业务的文件（研究状态、报告名归技能正文规定）
        workspace_capabilities = 'read_file / write_file / edit_file'
        if allow_shell:
            workspace_capabilities += ' / run_command'
        else:
            workspace_capabilities += '；Web 安全策略已关闭任意 shell 执行'
        sections.append(f'工作区已就绪（{workspace_capabilities}）。'
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
    tools.append(web_search_tool())
    tools.append(read_paper_tool(knowledge=KnowledgeService()))
    tools.append(fetch_url_tool())
    # 知识库三件套（paper_search / paper_detail / citation_graph）：与研究取证工具同层，
    # 由基座直接暴露——技能只写"怎么查"，能查什么由基座提供。
    tools.extend(item for item in knowledge_tools()
                 if not fast or item.spec.name != 'citation_graph')
    if fast:
        sections.append('''当前是「智能搜索」快速模式：目标是在 1–2 分钟内给出准确、有引用的直接回答。
- 学术问题用 paper_search 从 1–3 个不同角度检索（中文问题同时用英文标准术语查）；非学术时效信息用 web_search。
- 只有回答依赖具体数字、实验结果或方法细节时，才用 read_paper 读 1–2 篇核心论文的相关页（用 page_from/page_to 定位章节）。
- 不写 report.md 等工作区文件，答案直接写在回复里。
- 回答结构：第一段直接回答问题 → 3–6 条要点（每条承重主张带 [n] 引用）→ 代表论文（标题、年份、venue，一句话贡献）→ 「参考来源」列表（[n] 对应 paper_id 或 URL）。
- 只引用本次工具真实返回的来源，不凭记忆补充论文或数字；证据不足就直说。
- 如果问题明显需要系统性综述，先给出简要回答，并在结尾建议用户切换到深度模式。''')

    def agent_system(specs: Sequence[ToolSpec]) -> str:
        return compose_agent_system(specs, extra_sections=tuple(sections))

    return runtime_factory(system=agent_system, tools=tools or (), skills=store,
                           ask_user=not fast,  # 快速回答直接交付；其余路径允许反问用户
                           **hooks, **overrides)


