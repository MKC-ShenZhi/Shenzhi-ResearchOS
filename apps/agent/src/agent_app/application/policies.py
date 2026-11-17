"""Agent execution budgets and system prompt assembly."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from agent_app.execution.tools import ToolSpec

IDENTITY = '你是 ShenzhiAi，一个可以调用工具完成任务的智能体。'
TEMPERATURE = {'fast': 0.3, 'deep': 0.6, 'idea': 1.0, 'doubt': 0.85}
RUN_DEADLINE_S = {'fast': 180.0, 'deep': 900.0, 'idea': 900.0, 'doubt': 900.0}
TOOL_CALL_BUDGET = {'fast': 12, 'deep': 120, 'idea': 120, 'doubt': 120}


def compose_agent_system(specs: Sequence[ToolSpec], *, extra_sections: Sequence[str] = (),
                         guidelines: Sequence[str] = ()) -> str:
    sections = [IDENTITY]
    if specs:
        lines = ['可用工具：']
        for spec in specs:
            gloss = spec.snippet or spec.description.splitlines()[0].split('。')[0][:80]
            lines.append(f'- {spec.name}: {gloss}')
        sections.append('\n'.join(lines))
    rules = [*(rule for spec in specs for rule in spec.prompt_guidelines), *guidelines]
    if rules:
        sections.append('准则：\n' + '\n'.join(f'- {rule}' for rule in rules))
    now = datetime.now()
    sections.append(f'当前日期：{now:%Y-%m-%d}（周{"一二三四五六日"[now.weekday()]}）。')
    sections.extend(section for section in extra_sections if section)
    return '\n\n'.join(sections)


def run_deadline_s(mode: str) -> float:
    return RUN_DEADLINE_S.get(mode, RUN_DEADLINE_S['fast'])


def tool_call_budget(mode: str) -> int:
    return TOOL_CALL_BUDGET.get(mode, TOOL_CALL_BUDGET['fast'])
