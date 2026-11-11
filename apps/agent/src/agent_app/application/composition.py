"""Build one Agent Runtime from Agent-owned model and skill configuration."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from agent_app.execution.runtime import AgentRuntime
from agent_app.execution.tools import Tool
from agent_app.errors import BusinessError
from agent_app.extensions.skills import SkillStore, default_store
from agent_app.application.policies import (
    TEMPERATURE, compose_agent_system, run_deadline_s, tool_call_budget,
)
from agent_app.capabilities.fetch_url import fetch_url_tool
from agent_app.capabilities.read_paper import read_paper_tool
from agent_app.capabilities.web_search import web_search_tool
from agent_app.capabilities.knowledge import knowledge_tools
from agent_app.capabilities.chart_tools import chart_tool, image_search_tool
from agent_app.extensions.workspace import (
    Workspace, build_workspace_tools, ensure_session_workspace, mount_workspace,
    mount_workspace_into,
)
from agent_app.extensions.skills import sync_loaded_skill_scripts
from agent_app.integrations.llm.agent_stream import OpenAICompatProvider
from agent_app.integrations.llm.resolver import load_registry
from agent_app.integrations.backend.knowledge import BackendKnowledgeClient

PROJECT_CONTEXT_FILES = ('AGENTS.md', 'CLAUDE.md')
MAX_PROJECT_CONTEXT_CHARS = 60_000


def load_project_context(root: Path) -> str:
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


def default_runtime(*, skills: SkillStore | None = None, **overrides: Any) -> AgentRuntime:
    model = overrides.get('model')
    overrides['model'] = load_registry().resolve_model(
        model, 'agent', require_configured=False).spec.id
    overrides.setdefault('provider', OpenAICompatProvider())
    return AgentRuntime(skills=skills if skills is not None else default_store(), **overrides)


def build_runtime(*, runtime_factory: Callable[..., AgentRuntime] = default_runtime,
                  skills: SkillStore | None = None, mode: str = 'fast',
                  owner: str = 'system', workspace_id: str | None = None,
                  session_id: str | None = None, allow_shell: bool = False,
                  forced_skills: Sequence[str] = (),
                  **overrides: Any) -> AgentRuntime:
    """Assemble Agent-owned web evidence tools; product data adapters are injected separately."""
    fast = mode == 'fast' and not forced_skills
    store = skills if skills is not None else (SkillStore({}) if fast else default_store())
    knowledge = BackendKnowledgeClient()
    tools: list[Tool] = [web_search_tool(), read_paper_tool(knowledge=knowledge), fetch_url_tool()]
    tools.extend(item for item in knowledge_tools(knowledge)
                 if not fast or item.spec.name != 'citation_graph')
    root = None
    after_tool_call = None
    sections = []
    if session_id or workspace_id:
        root = (ensure_session_workspace(owner, session_id) if session_id
                else mount_workspace(workspace_id, owner).root)
        workspace = Workspace(root)
        tools.extend(build_workspace_tools(workspace, allow_shell=allow_shell))
        if workspace_id:
            mount_workspace_into(root, workspace_id, owner)
        after_tool_call = sync_loaded_skill_scripts(store, root)
        if not fast:
            tools.extend((chart_tool(workspace_root=root, session_id=session_id),
                          image_search_tool(workspace_root=root, session_id=session_id)))
        project_context = load_project_context(root)
        capabilities = 'read_file / write_file / edit_file'
        if allow_shell:
            capabilities += ' / run_command'
        else:
            capabilities += '；Web 安全策略已关闭任意 shell 执行'
        sections.append(
            f'工作区已就绪（{capabilities}）。中间状态与成果都写成工作区文件，完成后交付并给出文件路径。'
            '\n技能脚本在装载该技能后同步到 <技能名>/scripts/（在工作区根下执行）。'
            + (f'\n\n{project_context}' if project_context else '')
        )
    if forced_skills:
        selected = []
        for name in forced_skills:
            skill = store.get(name)
            if skill is None:
                raise BusinessError(20001, f'技能不存在: {name}')
            selected.append(f'用户显式选择了技能「{name}」，本轮必须遵循：\n\n{skill.body}')
        sections.append('\n\n'.join(selected))
    extra_sections = (
        '当前是科研与实时信息 Agent。需要外部证据时使用联网搜索、网页抓取或论文全文工具；'
        '只陈述工具实际返回的来源，不虚构来源。',
        *sections,
    )
    if fast:
        extra_sections += ('''当前是「智能搜索」快速模式：目标是在 1–2 分钟内给出准确、有引用的直接回答。
- 学术问题用 paper_search 从 1–3 个不同角度检索（中文问题同时用英文标准术语查）；非学术时效信息用 web_search。
- 只有回答依赖具体数字、实验结果或方法细节时，才用 read_paper 读 1–2 篇核心论文的相关页（用 page_from/page_to 定位章节）。
- 不写 report.md 等工作区文件，答案直接写在回复里。
- 回答结构：第一段直接回答问题 → 3–6 条要点（每条承重主张带 [n] 引用）→ 代表论文（标题、年份、venue，一句话贡献）→ 「参考来源」列表（[n] 对应 paper_id 或 URL）。
- 只引用本次工具真实返回的来源，不凭记忆补充论文或数字；证据不足就直说。
- 如果问题明显需要系统性综述，先给出简要回答，并在结尾建议用户切换到深度模式。''',)
    system = lambda specs: compose_agent_system(specs, extra_sections=extra_sections)
    overrides.setdefault('temperature', TEMPERATURE.get(mode, TEMPERATURE['fast']))
    overrides.setdefault('deadline_s', run_deadline_s(mode))
    overrides.setdefault('max_tool_calls', tool_call_budget(mode))
    overrides.setdefault('tool_budget', tool_call_budget(mode))
    overrides.setdefault('compaction', True)
    overrides.setdefault('ask_user', not fast)
    return runtime_factory(skills=store, system=system, tools=tools,
                           after_tool_call=after_tool_call, **overrides)
