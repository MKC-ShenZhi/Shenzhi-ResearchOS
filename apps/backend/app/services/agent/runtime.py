"""AgentRuntime：pi 式 turn 循环 + 服务端取消/超时/预算治理。

终态唯一真源是 RunResult（status 由 stop_reason 推导）：
- stop 事件（业务停止）→ 优雅收尾返回 stopped，run_end 照发；
- 外部 CancelledError（进程关闭/父任务取消）→ 终态落盘后原样重抛；
- transcript 永远合法：任何停止路径下未执行的 tool_call 都有合成 is_error
  结果（批次闭合），RunResult.messages 可原样作为下次 run 的 history。

turn = 一次模型调用 + 其工具执行；stop_reason=tool_calls 则开下一轮。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import model_config
from app.core.errors import BusinessError
from app.services.agent.compaction import (
    estimate_context_chars, format_file_operations, plan_compaction,
    split_off_summary, summarize, wrap_summary,
)
from app.services.agent.context import assemble
from app.services.agent.provider import (
    Finish, ModelProvider, ModelRequest, OpenAICompatProvider, ReasoningDelta, TextDelta, ToolCallEvent,
)
from app.services.agent.memory import Checkpoint, CheckpointStore
from app.services.agent.tools import (
    AfterToolCall, BeforeToolCall, Tool, ToolPolicy, ToolRegistry, ToolSpec,
)
from app.services.agent.types import (
    AgentEvent, AgentMessage, AssistantMessage, COMPACTION, DELTA, MESSAGE,
    RUN_END, RUN_START, RunChannel, RunResult, StopReason, TURN_START, message_to_dict,
    TOOL_CALL, TOOL_END, ToolCall, ToolResult, ToolResultMessage, TURN_END, UserMessage,
)

if TYPE_CHECKING:  # 能力层只在类型检查期出现：运行期内核不 import skills（依赖方向可验证）
    from app.services.agent.skills import Skill, SkillStore

logger = logging.getLogger('app.agent')

BUDGET_MESSAGE = '工具预算已耗尽，请基于已收集的证据直接作答。'
# 预算耗尽后的收尾：只拒绝调用，模型会一遍遍重复被拒的动作把轮次烧光（实测预算用完后
# 连续三批调用全被拒、每个 0ms，最终停止原因是 timeout，已收集的证据永远变不成答案）。
# 收尾模式收起检索/执行类工具、保留交付类工具（write_file / edit_file），把"没收工具"
# 与收尾指令成对给出，让证据能落成交付物。
BUDGET_FOLLOW_UP = (f'{BUDGET_MESSAGE}本轮已收起检索与执行类工具，仅保留交付类工具'
                    '（如 write_file / edit_file）：立即把已有证据整理成交付物（写成文件），'
                    '尚未覆盖的部分在交付物里如实说明。')
BUDGET_REJECT_MESSAGE = '本轮工具调用预算已耗尽，不再执行新的工具调用；请直接基于已收集的证据作答。'
# 收尾模式里模型仍发非交付调用（上游回放/自行编造）时的拒绝文案
WRAP_UP_REJECT_MESSAGE = ('运行进入收尾阶段（工具预算已耗尽或到达时间上限）：除交付类工具'
                          '（如 write_file / edit_file）外不再执行调用；请立即基于已收集的证据完成交付。')
DEADLINE_FOLLOW_UP = ('运行已到达时间上限：本轮只保留交付类工具（如 write_file / edit_file）。'
                      '请立即基于已收集的证据完成交付（写成文件），不要发起新的检索或执行。')
WRAP_UP_MAX_TURNS = 4  # deadline 交付窗口内最多收尾轮数，防模型在窗口里无限续写
TRUNCATED_CALL_MESSAGE = ('该响应因输出上限被截断，工具参数可能不完整，本次未执行；请重新发起完整的工具调用。'
                          '要写入的内容较长时不要一次写完：先写第一部分，再用 edit_file 分段续写。')
ABORTED_CALL_MESSAGE = 'Operation aborted'  # pi agent-loop:520-544 原句
PINNED_CONTEXT_RATIO = 0.6  # 技能正文（常驻内容）可占上下文预算的比例，其余留给对话与输出
# 当前轮组内工具结果的累计预算占比：一轮里反复调工具时，旧结果必须给新结果让位，
# 否则"每轮都能塞满预算"会把上下文管理变成必然失败（实测 20+ 次检索直接溢出）。
TURN_TOOL_BUDGET_RATIO = 0.5
# 提前交付引导阈值（源自 SZDR research-service 的 BUDGET_VISIBILITY_AT=0.83，语义加强）：
# 预算/时间用到该比例就要求模型**立即开始写交付物**，剩余额度只许补关键缺口——
# 而不是等预算用尽后由收尾模式补救（撞墙补救是兜底，主动收口才是常态）。
DELIVERY_NUDGE_AT = 0.83


class _RunState:
    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex
        self.seq = 0
        self.turn = 0
        self.messages: list[AgentMessage] = []
        self.stop_reason: StopReason | None = None
        self.error: BusinessError | None = None
        self.output: Any = None
        self.duration_ms = 0
        self.truncated = False
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.executed_tools = 0
        self.loaded_skills: set[str] = set()
        self.pinned_chars = 0
        self.deadline_at: float | None = None  # run 级 deadline 的单调钟截点（provider 重试参考）
        # 收尾模式（一次性闸门）：预算/时间撞墙后只保留交付类工具，直到 run 结束
        self.wrap_up = False
        self.budget_rejects = 0  # 本轮因预算被拒的调用数（撞墙检测依据，轮末清零）
        self.delivery_nudged = False  # 提前交付引导是否已注入过（一次性）
        # compaction 状态：最新摘要与文件清单（pi CompactionEntry 持久化要点）
        self.summary = ''
        self.read_files: list[str] = []
        self.modified_files: list[str] = []

    def event(self, turn: int, name: str, data: dict) -> AgentEvent:
        self.seq += 1
        return AgentEvent(self.seq, turn, name, data)

    def finalize(self, reason: StopReason, error: BusinessError | None = None,
                 output: Any = None) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
            self.error = error
            if output is not None:
                self.output = output

    def build(self) -> RunResult:
        assistant = next((m for m in reversed(self.messages) if isinstance(m, AssistantMessage)), None)
        return RunResult(
            stop_reason=self.stop_reason or StopReason.ERROR,
            messages=list(self.messages),
            final_text=assistant.content if assistant else '',
            final_reasoning=assistant.reasoning if assistant else '',
            output=self.output,
            turns=self.turn,
            duration_ms=self.duration_ms,
            error=self.error,
            truncated=self.truncated,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
        )


def _close_pending(state: _RunState, emit: Callable, reason: str) -> None:
    """批次闭合（幂等）：为最后一条 assistant 中尚无结果的 tool_call 合成 is_error 结果。

    这保证 RunResult.messages 在任何停止路径（max_turns / stop / 取消 / terminal
    直出 / 输出截断）下都是合法 transcript，可原样作为下次 run 的 history。
    """
    calls: tuple[ToolCall, ...] = ()
    for message in reversed(state.messages):
        if isinstance(message, AssistantMessage):
            calls = message.tool_calls
            break
    answered = {m.call_id for m in state.messages if isinstance(m, ToolResultMessage)}
    for call in calls:
        if call.call_id in answered:
            continue
        state.messages.append(ToolResultMessage(call.call_id, call.name, reason, is_error=True))
        emit(state.turn, TOOL_END, {'tool_call_id': call.call_id, 'name': call.name,
                                    'is_error': True, 'duration_ms': 0, 'summary': reason[:200]})


def _emitter(state: _RunState, on_event: Callable[[AgentEvent], None] | None) -> Callable:
    def emit(turn: int, name: str, data: dict) -> None:
        event = state.event(turn, name, data)
        if on_event is None:
            return
        try:
            on_event(event)  # 纯观察通道：回调异常不影响运行
        except Exception:
            logger.exception('agent.on_event 回调失败（已忽略）')

    return emit


@dataclass(frozen=True)
class _NaturalStop:
    """自然停止（STOP/LENGTH 且有正文）：尚未 finalize——_drive 先查预算收尾闩锁，
    不需要逼交付轮才落终态（pi：agent 会停时先 poll followUp 队列）。"""
    reason: StopReason


class AgentRuntime:
    """pi harness 循环的 Python 移植；每次 run 无状态，会话历史由调用方持有。"""

    def __init__(self, *,
                 provider: ModelProvider | None = None,
                 tools: Iterable[Tool] = (),
                 system: str | Callable[[Sequence[ToolSpec]], str] = '',
                 model: str | None = None,
                 temperature: float | None = None,
                 max_turns: int = 36,
                 deadline_s: float = 900.0,
                 max_tool_calls: int | None = None,
                 tool_budget: int | None = None,
                 max_context_chars: int = 180_000,
                 # 单条工具结果上限。**这里刻意不用 ×3**：安全上限放大只会让预算更早被撑爆
                 # （实测 24k×20 次检索 = 480k，直接越过 360k 预算），收紧反而更稳。
                 max_tool_result_chars: int = 8_000,
                 skills: SkillStore | None = None,
                 max_pinned_chars: int | None = None,
                 checkpoint_store: CheckpointStore | None = None,
                 compaction: bool = False,
                 compaction_at: float = 0.8,
                 # 压缩后保留的近期原文量。同样不用 ×3：留得越多，压缩腾出的空间越少。
                 compaction_keep_chars: int = 80_000,
                 max_summary_tokens: int | None = None,
                 tool_execution: str = 'parallel',  # pi 默认 parallel（types.ts:267 "Default: parallel"）
                 latent_tools: Sequence[str] = (),
                 ask_user: bool = False,
                 before_tool_call: BeforeToolCall | None = None,
                 after_tool_call: AfterToolCall | None = None):
        self.config = model_config()
        self.provider = provider or OpenAICompatProvider(self.config)
        self.checkpoint_store = checkpoint_store
        self.compaction = compaction
        self.compaction_at = compaction_at
        self.compaction_keep_chars = compaction_keep_chars
        self.tool_execution = tool_execution
        self.before_tool_call = before_tool_call
        self.after_tool_call = after_tool_call
        self._active_run = False  # pi agent.ts activeRun：同一实例并发 run 互斥
        # pi：maxTokens = min(0.8 × reserveTokens, model.maxTokens)；reserve 按字符预算折算
        reserve_chars = (1.0 - compaction_at) * max_context_chars
        self.max_summary_tokens = max_summary_tokens or max(256, int(reserve_chars * 0.8 / 4))

        # pinned 预算与上下文预算同源：技能正文是常驻内容，能吃多少由 max_context_chars
        # 决定，不设第二个魔数（此前写死 40k，而技能正文总量已 91k——装载第三个技能被拒）。
        self.max_pinned_chars = (max_pinned_chars if max_pinned_chars is not None
                                 else int(max_context_chars * PINNED_CONTEXT_RATIO))
        all_tools: list[Tool] = list(tools)
        tool_policy: ToolPolicy | None = None
        # 技能库为空时不注册 read_skill，也不装配策略：否则会向模型宣称一个没有内容的工具
        # （"不宣称不存在的工具"）。技能非空时按 skills 层默认实现装配（惰性导入，
        # 内核运行期不 import 能力层，依赖方向可验证）。
        if skills is not None and skills.names():
            from app.services.agent.skills import SkillPolicy, read_skill_tool
            all_tools.extend(skills.tools())
            all_tools.append(read_skill_tool(skills))
            tool_policy = SkillPolicy(skills, self.max_pinned_chars)
        self.tool_policy: ToolPolicy | None = tool_policy
        if ask_user:
            # 提问能力由组合根显式开启：纯离线批处理 runtime 不该带它（与 pi 把 question
            # 放在 extension 而非内核同一取舍）。
            from app.services.agent.ask_user import ask_user_tool
            all_tools.append(ask_user_tool())
        self.registry = ToolRegistry(all_tools, latent=latent_tools)
        # system 可为工厂：拿最终注册的工具清单生成系统提示（工具列表与 registry 恒同步，
        # pi coding-agent buildSystemPrompt 的 visibleTools 同机制）
        self.system = (system([tool.spec for tool in self.registry.tools.values()])
                       if callable(system) else system)
        # system 装配：业务 system → 技能清单（pi 两级注入；技能正文按需经 read_skill 装载）
        if skills is not None and skills.names():
            listing = skills.listing_prompt()
            if listing:
                self.system = f'{self.system}\n\n{listing}' if self.system else listing
        self.temperature = temperature
        self.max_turns = max_turns
        self.deadline_s = deadline_s
        # deadline 撞线后的交付窗口宽限：只带交付工具的收尾轮，把已收集证据写成交付物。
        # 上限 60s、下限 1s（测试用的极短 deadline 也给得出窗口）。
        self.deadline_grace_s = min(60.0, max(1.0, deadline_s * 0.5))
        self.max_tool_calls = max_tool_calls
        # 预算读数进系统提示：不给这个数，模型只能盲判——实测一次并行就烧掉大半预算，
        # 剩下一路撞到拒绝为止（基座机制，不是业务准则，故由内核生成）。
        self.tool_budget = tool_budget
        if tool_budget is not None:
            self.system += (f'\n\n本轮工具调用预算：{tool_budget} 次（整轮共用，用满即停）。'
                            '把次数留给最关键的证据；预算耗尽后不再执行工具调用，'
                            '只能基于已收集的证据交付，未覆盖的部分照实说明。')
        self.max_context_chars = max_context_chars
        self.max_tool_result_chars = max_tool_result_chars
        chosen = self.config.model if not model or model == 'default' else model
        if chosen not in self.config.models:
            raise BusinessError(20001, '所选模型未配置，请刷新后选择可用模型')
        self.model = chosen

    async def run(self, prompt: str, *, history: Sequence[AgentMessage] = (),
                  on_event: Callable[[AgentEvent], None] | None = None,
                  stop: asyncio.Event | None = None,
                  channel: RunChannel | None = None) -> RunResult:
        """跑完整个循环返回终态；观察走 on_event，业务停止走 stop 事件，
        运行中插话/排队追问走 channel（pi steer/followUp）。"""
        state = _RunState()
        state.messages = [*history, UserMessage(prompt)]
        emit = _emitter(state, on_event)
        return await self._drive(state, emit, stop, channel=channel)

    async def resume(self, checkpoint: Checkpoint, *,
                     on_event: Callable[[AgentEvent], None] | None = None,
                     stop: asyncio.Event | None = None,
                     channel: RunChannel | None = None) -> RunResult:
        """从 turn 边界快照继续运行（不追加新输入；最后一条消息须为 user/tool 结果）。

        恢复完整 run 级状态：用量、已执行工具数、pinned 预算、已装载技能、
        compaction 摘要与文件清单——续跑不会重置预算，也不会重复装载技能。
        """
        state = _RunState()
        state.run_id = checkpoint.run_id
        state.turn = checkpoint.turn
        state.messages = checkpoint.decoded_messages()
        # pi agent-loop:71-77/128-134：续跑前校验 transcript 形状，违规直接报错——
        # 空消息或末条是 assistant 都会让上游拒收，早失败好过带病运行
        if not state.messages:
            raise BusinessError(20001, 'checkpoint 不含任何消息，无法续跑')
        if isinstance(state.messages[-1], AssistantMessage):
            raise BusinessError(20001, 'checkpoint 末条是 assistant 消息，无法续跑（须为 user 或工具结果）')
        state.prompt_tokens = checkpoint.prompt_tokens
        state.completion_tokens = checkpoint.completion_tokens
        state.executed_tools = checkpoint.executed_tools
        state.pinned_chars = checkpoint.pinned_chars
        state.loaded_skills = set(checkpoint.loaded_skills)
        state.summary = checkpoint.summary
        state.read_files = list(checkpoint.read_files)
        state.modified_files = list(checkpoint.modified_files)
        emit = _emitter(state, on_event)
        logger.info('agent.run.resume run_id=%s from_turn=%s', state.run_id, checkpoint.turn)
        return await self._drive(state, emit, stop, resumed=True, channel=channel)

    async def _drive(self, state: _RunState, emit: Callable,
                     stop: asyncio.Event | None, *, resumed: bool = False,
                     channel: RunChannel | None = None) -> RunResult:
        # pi agent.ts:351-355：同一实例同时只允许一个 run——registry.enable / tool_policy
        # 都是 run 级可变状态，并发跑会互相踩。
        if self._active_run:
            raise BusinessError(20009, 'Agent 正在运行中，请等待本轮结束')
        self._active_run = True
        try:
            return await self._drive_locked(state, emit, stop, resumed=resumed, channel=channel)
        finally:
            self._active_run = False

    async def _drive_locked(self, state: _RunState, emit: Callable,
                            stop: asyncio.Event | None, *, resumed: bool = False,
                            channel: RunChannel | None = None) -> RunResult:
        def stop_requested() -> bool:
            return stop is not None and stop.is_set()

        def pending_steering() -> list[UserMessage]:
            return channel.drain_steering() if channel is not None else []

        state.deadline_at = time.monotonic() + self.deadline_s
        emit(0, RUN_START, {'run_id': state.run_id, 'model': self.model, 'resumed': resumed,
                            'tools': list(self.registry.enabled)})
        logger.info('agent.run.start run_id=%s model=%s resumed=%s tools=%s',
                    state.run_id, self.model, resumed, list(self.registry.enabled))
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.deadline_s):
                while True:
                    # steering poll ①：每轮请求前（pi agent-loop:168/257）
                    for message in pending_steering():
                        state.messages.append(message)
                        emit(state.turn, MESSAGE, {'text': message.text, 'kind': 'steer'})
                    if stop_requested():
                        _close_pending(state, emit, '未执行：已停止')
                        state.finalize(StopReason.CANCELLED)
                        break
                    outcome = await self._run_turn(state, emit, stop_requested, pending_steering)
                    # 每个完成的 turn 都落一次快照（含 max_turns 中断态——批次已闭合、可续跑）
                    if self.checkpoint_store is not None:
                        await self.checkpoint_store.save(self._checkpoint(state))
                    if outcome is not None and not isinstance(outcome, _NaturalStop):
                        break  # 终态（_run_turn 内已 finalize）
                    # 提前交付引导（一次）：预算/时间用到 83% 就要求模型**立即开始写交付物**，
                    # 剩余额度只许补关键缺口。等用尽再收尾是补救，主动收口才能把最后 17% 的
                    # 额度花在成稿上，而不是继续烧在检索上、撞墙时报告一个字没写。
                    if not state.delivery_nudged and not state.wrap_up:
                        budget_left = (self.max_tool_calls - state.executed_tools
                                       if self.max_tool_calls is not None else None)
                        time_left = (state.deadline_at - time.monotonic()
                                     if state.deadline_at is not None else None)
                        budget_near = (budget_left is not None and budget_left > 0
                                       and state.executed_tools
                                       >= self.max_tool_calls * DELIVERY_NUDGE_AT)
                        time_near = (time_left is not None and time_left > 0
                                     and time_left <= self.deadline_s * (1.0 - DELIVERY_NUDGE_AT))
                        if budget_near or time_near:
                            state.delivery_nudged = True
                            if budget_near:
                                note = (f'预算提示：工具调用已用 {state.executed_tools}/'
                                        f'{self.max_tool_calls} 次，剩 {budget_left} 次——'
                                        '现在就开始交付：把已有证据整理成报告（写成工作区文件），'
                                        '剩余次数只用于补最关键的证据缺口，不要再开新的检索方向。')
                            else:
                                note = (f'时间提示：本轮剩余时间约 {int(time_left)} 秒——'
                                        '现在就开始交付：把已有证据整理成报告（写成工作区文件），'
                                        '不要再开新的检索方向。')
                            state.messages.append(UserMessage(note))
                            emit(state.turn, MESSAGE, {'text': note, 'kind': 'system'})
                    # 预算撞墙（本轮有调用因预算被拒）= 模型真的撞上了墙：立即进入收尾模式，
                    # 下一请求只保留交付类工具。用户插话优先：插话在途时推迟到后面的位点。
                    if (self._budget_spent(state) and state.budget_rejects > 0
                            and not state.wrap_up and not pending_steering()):
                        self._enter_wrap_up(state, emit)
                    state.budget_rejects = 0
                    # steering poll ②：turn_end 之后（pi agent-loop:257）——有插话就再开一轮
                    steered = pending_steering()
                    for message in steered:
                        state.messages.append(message)
                        emit(state.turn, MESSAGE, {'text': message.text, 'kind': 'steer'})
                    if steered:
                        continue
                    if isinstance(outcome, _NaturalStop):
                        if self._budget_spent(state) and not state.wrap_up:
                            # 预算已耗尽而模型停笔：先逼一次只带交付工具的收尾轮，再谈停止
                            self._enter_wrap_up(state, emit)
                        else:
                            state.finalize(outcome.reason)
                            break
        except TimeoutError:
            _close_pending(state, emit, '未执行：运行超时')
            # 交付窗口：deadline 常撞在工具批次中间，直接终态会把已收集的证据整批扔掉
            # （实测一批 paper_search 全部 0ms 失败后什么都不剩）。用一笔宽限预算做收尾轮：
            # 只保留交付类工具，让模型把已有证据写成交付物，然后仍以 timeout 终态交付。
            state.wrap_up = True
            state.messages.append(UserMessage(DEADLINE_FOLLOW_UP))
            emit(state.turn, MESSAGE, {'text': DEADLINE_FOLLOW_UP, 'kind': 'system'})
            try:
                async with asyncio.timeout(self.deadline_grace_s):
                    for _ in range(WRAP_UP_MAX_TURNS):
                        outcome = await self._run_turn(state, emit, stop_requested, pending_steering)
                        if outcome is None:
                            continue  # 本轮执行了交付工具 → 让模型继续收口
                        break  # 自然停笔（交付完成）或已被终态化（停止/错误）
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('agent.run.delivery_window run_id=%s', state.run_id)
            state.finalize(StopReason.TIMEOUT)
        except asyncio.CancelledError:
            _close_pending(state, emit, '未执行：运行被取消')
            state.finalize(StopReason.CANCELLED)
            state.duration_ms = int((time.monotonic() - started) * 1000)
            logger.info('agent.run.end run_id=%s status=stopped(cancelled) turns=%s',
                        state.run_id, state.turn)
            raise
        except BusinessError as exc:
            # transcript 恒闭合（types.py 的契约）：任何失败路径都不得留下未答的 tool_call，
            # 否则这份 messages 作为 history/resume 再发就会被上游拒收
            _close_pending(state, emit, f'未执行：{exc.message}')
            state.finalize(StopReason.ERROR, exc)
        except Exception:
            logger.exception('agent.run.error run_id=%s', state.run_id)
            _close_pending(state, emit, '未执行：运行发生错误')
            state.finalize(StopReason.ERROR, BusinessError(20004, 'Agent 运行发生错误，请重试'))
        state.duration_ms = int((time.monotonic() - started) * 1000)
        result = state.build()
        emit(state.turn, RUN_END, {
            'status': result.status, 'stop_reason': result.stop_reason.value,
            'turns': result.turns, 'duration_ms': result.duration_ms,
            'error': ({'code': result.error.code, 'message': result.error.message}
                      if result.error else None),
        })
        logger.info('agent.run.end run_id=%s status=%s turns=%s duration_ms=%s',
                    state.run_id, result.status, result.turns, result.duration_ms)
        return result

    def _budget_spent(self, state: _RunState) -> bool:
        """工具调用预算是否已耗尽（未配置预算时恒 False）。"""
        return self.max_tool_calls is not None and state.executed_tools >= self.max_tool_calls

    def _is_delivery(self, name: str) -> bool:
        tool = self.registry.tools.get(name)
        return tool is not None and tool.spec.delivery

    def delivery_wire(self) -> list[dict]:
        """收尾模式的工具清单：仅交付类（write_file / edit_file 等），撞墙后仍能落盘交付。"""
        return self.registry.wire([name for name in self.registry.enabled
                                   if self._is_delivery(name)])

    def _enter_wrap_up(self, state: _RunState, emit: Callable) -> None:
        """进入收尾模式（一次性）：收起检索/执行类工具，并告知模型原因与交付要求。"""
        state.wrap_up = True
        state.messages.append(UserMessage(BUDGET_FOLLOW_UP))
        emit(state.turn, MESSAGE, {'text': BUDGET_FOLLOW_UP, 'kind': 'system'})

    def _checkpoint(self, state: _RunState) -> Checkpoint:
        """turn 边界快照（含 max_turns/停止中断态——批次已闭合、可续跑）。"""
        return Checkpoint(
            run_id=state.run_id, turn=state.turn,
            messages=[message_to_dict(m) for m in state.messages],
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
            summary=state.summary,
            read_files=state.read_files,
            modified_files=state.modified_files,
            loaded_skills=sorted(state.loaded_skills),
            pinned_chars=state.pinned_chars,
            executed_tools=state.executed_tools)

    async def _run_turn(self, state: _RunState, emit: Callable, stop_requested: Callable,
                        pending_steering: Callable[[], list[UserMessage]]) -> StopReason | None:
        """执行一轮：请求 → 流式 → 工具批 → turn_end（pi agent-loop 的 turn 段）。

        返回非 None 表示运行已终态化；`_NaturalStop` 表示本轮无工具调用（agent 本会停止）；
        None 表示继续下一轮。位点顺序照 pi：turn_end 在工具执行**之后**发，
        steering / 预算治理由 _drive 在 turn_end 之后依次处理。
        """
        state.turn += 1
        emit(state.turn, TURN_START, {'turn': state.turn})
        await self._maybe_compact(state, emit)  # pi transformContext 位点：下一请求前按需压缩
        # 压缩是长耗时准备，之后补一次 steering poll（pi agent-loop:194-196）——
        # 否则压缩期间到达的插话要么被折进摘要、要么白等一轮。
        for message in pending_steering():
            state.messages.append(message)
            emit(state.turn, MESSAGE, {'text': message.text, 'kind': 'steer'})
        # 收尾模式（预算/时间撞墙）：只把交付类工具放进请求，模型只能交付而不是继续检索
        tools_wire = self.delivery_wire() if state.wrap_up else self.registry.wire()
        wire, truncated = assemble(
            self.system, state.messages,
            max_chars=self.max_context_chars,
            max_tool_result_chars=self.max_tool_result_chars,
            # 当前轮组内工具结果的累计上限：一轮里调很多次工具时，只保留最近的，
            # 更早的退化成开头 + 提示（实测 20+ 次检索把预算撑爆）。
            max_turn_tool_chars=max(int(self.max_context_chars * TURN_TOOL_BUDGET_RATIO), 8_000),
            tools_wire_chars=len(str(tools_wire)),
        )
        state.truncated = state.truncated or truncated
        request = ModelRequest(self.model, wire, tools_wire, self.temperature,
                               deadline_at=state.deadline_at)
        assistant = AssistantMessage()
        state.messages.append(assistant)
        delta_buffer: list[str] = []
        provider_error = ''
        async with aclosing(self.provider.stream(request)) as stream:
            async for event in stream:
                if stop_requested():
                    if delta_buffer:
                        emit(state.turn, DELTA, {'text': ''.join(delta_buffer)})
                        delta_buffer.clear()
                    break
                if isinstance(event, TextDelta):
                    assistant.content += event.text
                    delta_buffer.append(event.text)
                    if sum(len(piece) for piece in delta_buffer) >= 24:
                        emit(state.turn, DELTA, {'text': ''.join(delta_buffer)})
                        delta_buffer.clear()
                elif isinstance(event, ReasoningDelta):
                    assistant.reasoning += event.text
                    emit(state.turn, DELTA, {'reasoning': event.text})
                elif isinstance(event, ToolCallEvent):
                    assistant.tool_calls += (event.call,)
                    # 事件是传输层（SSE/CLI）：参数按文本发出，前端与历史回传的
                    # `arguments: string` 契约不变；内部类型是解析后的对象
                    emit(state.turn, TOOL_CALL, {'tool_call_id': event.call.call_id,
                                                 'name': event.call.name,
                                                 'arguments': json.dumps(event.call.arguments,
                                                                         ensure_ascii=False)})
                elif isinstance(event, Finish):
                    if delta_buffer:
                        emit(state.turn, DELTA, {'text': ''.join(delta_buffer)})
                        delta_buffer.clear()
                    assistant.stop_reason = event.stop_reason
                    provider_error = event.error_message
                    if event.usage is not None:
                        state.prompt_tokens += event.usage.prompt_tokens
                        state.completion_tokens += event.usage.completion_tokens
                        # usage 挂最终消息（pi ai/types.ts）：compaction 优先用真实用量估算
                        assistant.usage_tokens = (event.usage.prompt_tokens
                                                   + event.usage.completion_tokens)
        calls = assistant.tool_calls
        # stop_reason 从不改写（pi agent-loop:222-233）：是否续跑只看"有没有工具调用"，
        # transcript 里保留模型给的原始语义（此前把 stop+calls 改成 tool_calls、
        # 把空 calls 改成 stop，等于篡改事实）。
        outcome: StopReason | None = None
        if stop_requested():
            _close_pending(state, emit, '未执行：已停止')
            state.finalize(StopReason.CANCELLED)
            outcome = StopReason.CANCELLED
        elif assistant.stop_reason is StopReason.ERROR:
            # provider 把 content_filter / 未知 finish_reason 映射成 error（pi 同口径）：
            # 批次照常闭合，终态带上上游给的原文，不再伪装成"正常说完"
            _close_pending(state, emit, '未执行：模型返回错误')
            state.finalize(StopReason.ERROR,
                           BusinessError(20004, provider_error or '模型返回错误，请重试'))
            outcome = StopReason.ERROR
        elif calls and assistant.stop_reason is StopReason.LENGTH:
            # 输出被截断：参数可能不完整，全部判失败让模型重发（pi agent-loop:229-232）。
            # 该轮同样计入轮数治理，LENGTH 连击不会绕过 max_turns。
            _close_pending(state, emit, TRUNCATED_CALL_MESSAGE)
        elif calls and state.turn >= self.max_turns:
            _close_pending(state, emit, '未执行：已达到最大轮数限制')
            state.finalize(StopReason.MAX_TURNS, BusinessError(20009, 'Agent 已达到最大轮数限制'))
            outcome = StopReason.MAX_TURNS
        elif calls:
            # 收尾模式下非交付调用在 _run_tools 预检里逐个拒绝，交付类照常执行
            outcome = await self._run_tools(state, assistant, emit, stop_requested)
        elif not assistant.content and not assistant.reasoning:
            # pi agent-loop:226：空响应也照常收尾（run 判成功），不当错误——
            # 真正的异常停止由 provider 映射成 error/aborted 停止原因。
            logger.warning('agent.empty_response run_id=%s turn=%s stop_reason=%s',
                           state.run_id, state.turn, assistant.stop_reason.value)
        if outcome is not None:
            # 终态路径也要发 turn_end（pi：每个 turn 都以 turn_end 收尾，再 agent_end）
            emit(state.turn, TURN_END, {'turn': state.turn,
                                        'stop_reason': assistant.stop_reason.value,
                                        'truncated': truncated,
                                        'tool_calls': len(calls), 'tool_errors': 0})
            return outcome
        # turn_end 在工具执行之后发（pi agent-loop:243），带上本批工具结果概况
        batch = [m for m in state.messages if isinstance(m, ToolResultMessage)][-len(calls):] \
            if calls else []
        emit(state.turn, TURN_END, {'turn': state.turn,
                                    'stop_reason': assistant.stop_reason.value,
                                    'truncated': truncated,
                                    'tool_calls': len(calls),
                                    'tool_errors': sum(1 for m in batch if m.is_error)})
        if not calls:
            return _NaturalStop(assistant.stop_reason)
        return None

    async def _maybe_compact(self, state: _RunState, emit: Callable) -> None:
        """占用达阈值且历史足够长时压缩：近期按预算保留原文，旧的折叠为结构化摘要
        （pi compaction.ts 语义；触发估算优先真实用量，见 compaction.estimate_context_chars）。"""
        if not self.compaction:
            return
        tools_wire_chars = len(str(self.registry.wire()))
        used = estimate_context_chars(state.messages, system_chars=len(self.system),
                                      tools_wire_chars=tools_wire_chars)
        if used < self.compaction_at * self.max_context_chars:
            return
        plan = plan_compaction(state.messages, keep_recent_chars=self.compaction_keep_chars,
                               prior_read=state.read_files, prior_modified=state.modified_files,
                               system_chars=len(self.system), tools_wire_chars=tools_wire_chars)
        if plan is None:
            return
        # 旧摘要走 previous-summary 通道迭代更新，不重复进对话（跨 run 时从历史消息恢复）
        fold, recovered = split_off_summary(plan.fold_messages)
        previous_summary = state.summary or recovered
        if not fold:
            return
        summary = await summarize(self.provider, self.model, fold,
                                  previous_summary=previous_summary,
                                  max_summary_tokens=self.max_summary_tokens)
        if summary is None:
            return  # 摘要失败 → 回退 assemble 确定性截断，run 不失败
        summary += format_file_operations(plan.read_files, plan.modified_files)
        new_messages = [UserMessage(wrap_summary(summary)), *plan.retained]
        after = estimate_context_chars(new_messages, system_chars=len(self.system),
                                       tools_wire_chars=tools_wire_chars)
        state.messages = new_messages
        state.summary = summary
        state.read_files = plan.read_files
        state.modified_files = plan.modified_files
        emit(state.turn, COMPACTION, {'before_chars': plan.chars_before, 'after_chars': after,
                                      'read_files': len(plan.read_files),
                                      'modified_files': len(plan.modified_files)})
        logger.info('agent.compaction run_id=%s before=%s after=%s', state.run_id,
                    plan.chars_before, after)

    async def _run_tools(self, state: _RunState, assistant: AssistantMessage, emit: Callable,
                         stop_requested: Callable) -> StopReason | None:
        """执行本轮工具调用；terminal 直出或 stop 时终态化。

        parallel 模式：先全部 prepare（校验+before 钩子，pi executeToolCallsParallel 的
        预检段），再并发执行，结果按调用顺序回填 transcript；任一工具声明
        execution_mode='sequential' 则整批退回顺序执行（pi hasSequentialToolCall）。
        """
        calls = list(assistant.tool_calls)
        if self.tool_execution == 'parallel':
            needs_sequential = any(
                self.registry.tools.get(call.name) is not None
                and self.registry.tools[call.name].spec.execution_mode == 'sequential'
                for call in calls)
        else:
            needs_sequential = True
        if not needs_sequential:
            return await self._run_tools_parallel(state, assistant, calls, emit, stop_requested)
        return await self._run_tools_sequential(state, assistant, calls, emit, stop_requested)

    async def _run_tools_sequential(self, state: _RunState, assistant: AssistantMessage,
                                    calls: list[ToolCall], emit: Callable,
                                    stop_requested: Callable) -> StopReason | None:
        for call in calls:
            if stop_requested():
                break
            result, duration_ms = await self._execute_call(state, call)
            self._record_tool_result(state, emit, call, result, duration_ms)
            if result.terminal is not None:
                _close_pending(state, emit, '未执行：运行已交付最终制品')
                return self._finalize_terminal(state, result.terminal)
            activated = self.registry.enable(result.added_tool_names)
            if activated:
                emit(state.turn, 'tools_enabled', {'names': activated})
        if stop_requested():
            _close_pending(state, emit, '未执行：已停止')
            state.finalize(StopReason.CANCELLED)
            return StopReason.CANCELLED
        return None

    async def _run_tools_parallel(self, state: _RunState, assistant: AssistantMessage,
                                  calls: list[ToolCall], emit: Callable,
                                  stop_requested: Callable) -> StopReason | None:
        # 1) 预检：策略拦截 + 预算 + 校验 + before 钩子逐个过（立即结果直接落袋）
        # 预算按"预留"口径在预检里逐个记账：只看 state.executed_tools 会让同一批里的每个调用
        # 都读到批次开始前的旧值，于是一批 12 个调用可以整体越过预算（实测预算 24 跑出 12 次
        # 成功、再成批被拒，就是这个洞）。放行即 +1，被拒的批次不再继续放行。
        prepared: list[tuple[ToolCall, 'PreparedCall | None', ToolResult | None]] = []
        for call in calls:
            if stop_requested():
                break
            if state.wrap_up and not self._is_delivery(call.name):
                # 收尾模式：非交付调用一律拒绝（预算/时间两个来历同一文案），交付类放行
                prepared.append((call, None, ToolResult(call.call_id, call.name,
                                                        WRAP_UP_REJECT_MESSAGE, is_error=True)))
                continue
            if not state.wrap_up and self._budget_spent(state):
                state.budget_rejects += 1
                prepared.append((call, None, ToolResult(call.call_id, call.name,
                                                        BUDGET_REJECT_MESSAGE, is_error=True)))
                continue
            if self.tool_policy is not None:
                blocked = self.tool_policy.intercept(call, state)
                if blocked is not None:
                    prepared.append((call, None, blocked))
                    continue
            outcome = await self.registry.prepare(call, before=self.before_tool_call)
            # 未知工具 / 校验失败 / 钩子阻断 → 立即结果（pi prepareToolCall 的三种短路）；
            # 其余进并发执行。两者位置写反会让被阻断的调用当成待执行项送进去。
            if isinstance(outcome, ToolResult):
                prepared.append((call, None, outcome))
            else:
                state.executed_tools += 1  # 放行即占名额
                prepared.append((call, outcome, None))
        # 2) 并发执行（无准备项的跳过）；wait 保证取消安全
        async def run_one(call: ToolCall, item: 'PreparedCall | None') -> tuple[ToolResult, int]:
            started = time.monotonic()
            result = await self.registry.execute_prepared(item, after=self.after_tool_call)
            if self.tool_policy is not None:
                result = self.tool_policy.settle(call, result, state)
            return result, int((time.monotonic() - started) * 1000)
        tasks = {asyncio.ensure_future(run_one(call, item)): (call, immediate)
                 for call, item, immediate in prepared if item is not None}
        executed: dict[str, tuple[ToolResult, int]] = {}
        if tasks:
            # pi agent-loop:520-544：中止时未启动/进行中的调用合成 "Operation aborted" 结果，
            # 而不是等它们全部跑完——停止请求必须立刻生效。
            try:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
            except asyncio.CancelledError:
                # deadline/外层取消打在 wait 上：在途任务必须就地取消，否则成为孤儿
                #（继续占用连接与进程，其结果也永远回不到 transcript——transcript 由
                # 上层的 _close_pending 兜底闭合）。
                for future in tasks:
                    future.cancel()
                raise
            for future in done:
                call = tasks[future][0]
                try:
                    executed[call.call_id] = future.result()
                except asyncio.CancelledError:
                    executed[call.call_id] = (ToolResult(call.call_id, call.name,
                                                         ABORTED_CALL_MESSAGE, is_error=True), 0)
            for future in pending:  # 理论上 ALL_COMPLETED 下为空，防御性取消
                future.cancel()
        # 3) 按调用顺序回填（pi：tool_execution_end 按完成序，结果消息按源序）
        terminal_output = None
        for call, item, immediate in prepared:
            if immediate is not None:
                result, duration_ms = immediate, 0
            elif call.call_id in executed:
                result, duration_ms = executed[call.call_id]
            else:  # stop 打断未执行的
                continue
            self._record_tool_result(state, emit, call, result, duration_ms)
            self.registry.enable(result.added_tool_names)
            if result.terminal is not None and terminal_output is None:
                terminal_output = result.terminal
        if terminal_output is not None:
            _close_pending(state, emit, '未执行：运行已交付最终制品')
            return self._finalize_terminal(state, terminal_output)
        if stop_requested():
            _close_pending(state, emit, '未执行：已停止')
            state.finalize(StopReason.CANCELLED)
            return StopReason.CANCELLED
        return None

    def _record_tool_result(self, state: _RunState, emit: Callable, call: ToolCall,
                            result: ToolResult, duration_ms: int) -> None:
        state.messages.append(ToolResultMessage(result.call_id, result.name,
                                                result.content, result.is_error, result.pinned))
        emit(state.turn, TOOL_END, {'tool_call_id': result.call_id, 'name': result.name,
                                    'is_error': result.is_error, 'duration_ms': duration_ms,
                                    'summary': result.content[:200]})

    @staticmethod
    def _finalize_terminal(state: _RunState, output: Any) -> StopReason:
        """terminal 制品 → 终态：问题制品停为 awaiting_input，其余制品为正常交付。

        收口一处的原因：提问与交付走的是同一条直出通道，停轮语义必须只在这里判定，
        否则新增制品类型时每个分支都要改（此前两处硬编码 STOP）。
        """
        if isinstance(output, dict) and output.get('kind') == 'question':
            state.finalize(StopReason.AWAITING_INPUT, output=output)
            return StopReason.AWAITING_INPUT
        state.finalize(StopReason.STOP, output=output)
        return StopReason.STOP

    async def _execute_call(self, state: _RunState, call: ToolCall) -> tuple[ToolResult, int]:
        """单个工具调用：策略拦截（如技能重复装载）+ 工具预算 + 分发 + 策略结算。"""
        if state.wrap_up and not self._is_delivery(call.name):
            return ToolResult(call.call_id, call.name, WRAP_UP_REJECT_MESSAGE, is_error=True), 0
        if self.tool_policy is not None:
            blocked = self.tool_policy.intercept(call, state)
            if blocked is not None:
                return blocked, 0
        if not state.wrap_up and self._budget_spent(state):
            state.budget_rejects += 1
            return ToolResult(call.call_id, call.name, BUDGET_REJECT_MESSAGE, is_error=True), 0
        # 放行即占名额（与并行路径同一口径）
        state.executed_tools += 1
        tool_started = time.monotonic()
        result = await self.registry.dispatch(
            call, before=self.before_tool_call, after=self.after_tool_call)
        if self.tool_policy is not None:
            result = self.tool_policy.settle(call, result, state)
        return result, int((time.monotonic() - tool_started) * 1000)
