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


# run 的时间预算（秒）与工具调用次数（次），按模式给。与 model_provider.TEMPERATURE
# 同为"按模式的业务策略"。
#
# 数字对齐 SZDR（前代研究产品）的实测形态：15 分钟 run 上限（RESEARCH_TIMEOUT_MS=900_000）
# + 120 次工具调用，一种 run shape、深度由模型经技能自决。此前的"延迟优先"收窄（60s/200s、
# 24/60 次）实测装不下一次像样的检索综述：13 次 paper_search ×5s 加模型轮次就耗尽 deep 的
# 200s，八阶段流程必然撞墙。撞墙治理已由收尾模式/交付窗口兜底（超时也交付已收集的证据），
# 故回到 SZDR 的量级；deadline 是上限不是目标，快问题照样快回。
RUN_DEADLINE_S = {'fast': 900.0, 'deep': 900.0, 'idea': 900.0, 'doubt': 900.0}
# 工具调用预算：让 run 有明确的收尾压力，也是"边际产出"的硬信号——用完就交付，
# 缺口按停止条件里的"预算终止 ≠ 查全"如实申报。预算/时间用到 83% 即注入交付指令
# （runtime.DELIVERY_NUDGE_AT，源自 SZDR 的 BUDGET_VISIBILITY_AT）：要求模型立即开始
# 写交付物，而不是等预算用尽后才由收尾模式补救。
TOOL_CALL_BUDGET = {'fast': 120, 'deep': 120, 'idea': 120, 'doubt': 120}


def run_deadline_s(mode: str) -> float:
    """模式的 run 时间预算（service 与 CLI 共用，避免两处各写一个数）。"""
    return RUN_DEADLINE_S.get(mode, RUN_DEADLINE_S['fast'])


def tool_call_budget(mode: str) -> int:
    """模式的工具调用预算（service 与 CLI 共用）。"""
    return TOOL_CALL_BUDGET.get(mode, TOOL_CALL_BUDGET['fast'])
