"""Agent 基座的产品策略：系统提示骨架与按模式的运行预算。

这些是**业务策略**（谁在什么模式下、以什么身份工作），不是基座机制：
内核（runtime / tools / provider / context）不认识它们。

提示词的取舍：**只保留骨架，不照搬任何现成 agent 的准则、也不自作主张往里加内容**。
骨架 = 身份 + 当前可用工具清单 + 当前日期。工具自己的 `prompt_guidelines` 由工具在挂载时
贡献（工具知道自己的注意事项），业务侧要加内容就通过 `extra_sections` / `guidelines` 显式传入——
基座本身不预设写作风格、工作纪律或能力边界的说法。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.services.agent.tools import ToolSpec

IDENTITY = '你是 ShenzhiAi，一个可以调用工具完成任务的智能体。'


def compose_agent_system(specs: Sequence[ToolSpec], *, extra_sections: Sequence[str] = (),
                         guidelines: Sequence[str] = ()) -> str:
    """系统提示装配：身份 → 可用工具清单 → 工具自带准则 → 环境 → 附加段落。

    工具清单按最终注册表生成（不宣称不存在的工具）；工具专属准则由 `ToolSpec.prompt_guidelines`
    随挂载出现；`guidelines` / `extra_sections` 是业务侧的显式注入点。
    日期必须由 harness 提供（模型本身无时钟）。
    """
    sections = [IDENTITY]
    if specs:
        def gloss(description: str) -> str:
            first = description.splitlines()[0].split('。')[0].strip()
            return first[:80] or description.strip()[:80]

        lines = ['可用工具：']
        lines += [f'- {spec.name}: {spec.snippet or gloss(spec.description)}' for spec in specs]
        sections.append('\n'.join(lines))
    rules = [*(rule for spec in specs for rule in spec.prompt_guidelines), *guidelines]
    if rules:
        sections.append('准则：\n' + '\n'.join(f'- {rule}' for rule in rules))
    now = datetime.now()
    weekday = '一二三四五六日'[now.weekday()]
    sections.append(f'当前日期：{now.strftime("%Y-%m-%d")}（周{weekday}）。')
    sections.extend(section for section in extra_sections if section)
    return '\n\n'.join(sections)


# run 的时间预算（秒），按模式给。与 model_provider.TEMPERATURE 同为"按模式的业务策略"。
RUN_DEADLINE_S = {'fast': 2700.0, 'deep': 5400.0, 'idea': 2700.0, 'doubt': 2700.0}


def run_deadline_s(mode: str) -> float:
    """模式的 run 时间预算（service 与 CLI 共用，避免两处各写一个数）。"""
    return RUN_DEADLINE_S.get(mode, RUN_DEADLINE_S['fast'])
