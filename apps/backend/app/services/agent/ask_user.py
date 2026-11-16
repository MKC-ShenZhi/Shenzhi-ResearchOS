"""ask_user：基座内置的"向用户提问"工具（Claude Code AskUserQuestion / pi question 的契约）。

设计取舍（三个参照的对照结论）：

- **pi `question`／`questionnaire`**：同轮阻塞——工具执行里 `await ctx.ui.custom(...)` 等用户在
  TUI 里选完，然后把答案当作工具结果回喂模型，同一轮继续。非交互模式直接报"UI 不可用"。
  这适用于"进程即 UI"的本地终端。
- **Claude Code `AskUserQuestion`**：模型调用工具提出问题（可多问），宿主把问题呈现给用户，
  答案回到会话里继续。
- **OpenAI Agents SDK / LangGraph**：工具声明需要批准 → 运行挂起 → 序列化 RunState →
  稍后用决策恢复。

本基座是**服务端 run + SSE**，一个 run 可能跑十几分钟、连接可能断开，因此**不做同轮阻塞**：
提问走基座既有的 terminal 直出通道——问题本身是这一轮的制品，run 干净停轮（保留完整合法
transcript），用户的选择作为**下一条用户消息**回传。这与 SZDR 引擎的 clarify 分支同形，
也是唯一不需要挂起/恢复引擎的做法。

为什么不用挂起/恢复：基座已有 Checkpoint/resume，但那是给崩溃续跑用的；把它用于"等用户
输入"意味着 run 要跨用户交互存活、还要新增恢复端点与状态清理。而 transcript 已经是自洽的
（批次闭合保证），下一条消息续跑等价且更简单。

**一次一个问题**：曾经支持一次问 1-4 个（学 Claude Code 的多问题表单），但那需要"部分已确认"
的中间状态——点选项只填入、还要用户找地方提交，界面上就没有那个地方，于是点完卡住。
一次一个问题配合"点选项即发送"，没有中间状态要管，也不会让用户对着卡片发愣。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import BusinessError
from app.services.agent.tools import Tool, ToolOutput, tool

MAX_OPTIONS = 6
MAX_LABEL_CHARS = 200


class QuestionOption(BaseModel):
    """一个候选项。value 是回传给模型的值，label 是展示文案（缺省用 value）。"""
    value: str
    label: str | None = None
    description: str | None = None


class AskUserArgs(BaseModel):
    question: str = Field(description='要问用户的问题（一次只问一个）')
    options: list[QuestionOption] = Field(default_factory=list,
                                          description='候选选项；给 2-6 个具体、互斥的选项')
    allow_other: bool = Field(default=True, description='是否允许用户自由作答（默认允许）')
    header: str | None = Field(default=None, description='可选的短标题，如"研究范围"')


def _normalize(args: AskUserArgs) -> dict[str, Any]:
    """校验并规范化问题；返回 terminal 制品。"""
    prompt = args.question.strip()
    if not prompt:
        raise BusinessError(20001, 'ask_user 需要 question')
    if len(args.options) > MAX_OPTIONS:
        raise BusinessError(20001, f'ask_user 选项过多（最多 {MAX_OPTIONS} 个）')
    options = []
    for option in args.options:
        value = option.value.strip()
        if not value:
            continue
        options.append({
            'value': value[:MAX_LABEL_CHARS],
            'label': (option.label or value).strip()[:MAX_LABEL_CHARS],
            'description': (option.description or '').strip() or None,
        })
    if not options and not args.allow_other:
        raise BusinessError(20001, 'ask_user 既无选项又不允许自由作答，用户无法回答')
    header = (args.header or '').strip() or None
    return {'kind': 'question', 'question': prompt, 'options': options,
            'allow_other': bool(args.allow_other), 'header': header}


def ask_user_tool() -> Tool:
    """内置 ask_user 工具；由组合根按需注册（默认不进每个 runtime）。

    注册即意味着"这个 runtime 支持向用户提问"——纯离线的批处理 runtime 不该带它，
    因此不做无条件内置（与 pi 把 question 放在 extension/plan-mode 里同一取舍）。
    """

    @tool(name='ask_user',
          description='向用户提问并等待回答（问题展示为可点选的选项）；一次一个问题，'
                      '用户点选项即作为回答发回、本轮结束。',
          params=AskUserArgs,
          snippet='向用户提问（选项式），本轮停下等回答')
    async def ask_user(args: AskUserArgs) -> str | ToolOutput:
        artifact = _normalize(args)
        return ToolOutput(
            content=f'已向用户提问并等待回答：{artifact["question"][:200]}',
            terminal=artifact)

    return ask_user
