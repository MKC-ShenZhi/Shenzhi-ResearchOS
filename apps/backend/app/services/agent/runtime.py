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
    estimate_context_chars, extract_file_ops, format_file_operations, plan_compaction,
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
    AgentEvent, AgentMessage, AssistantMessage, COMPACTION, DELTA, FollowUpContext, MESSAGE, NextTurn,
    RUN_END, RUN_START, RunChannel, RunResult, StopContext, StopReason, TURN_START, message_to_dict,
    TOOL_CALL, TOOL_END, ToolCall, ToolResult, ToolResultMessage, TURN_END, UserMessage,
)

if TYPE_CHECKING:  # 能力层只在类型检查期出现：运行期内核不 import skills（依赖方向可验证）
    from app.services.agent.skills import Skill, SkillStore

logger = logging.getLogger('app.agent')

BUDGET_MESSAGE = '工具预算已耗尽，请基于已收集的证据直接作答。'
TRUNCATED_CALL_MESSAGE = ('该响应因输出上限被截断，工具参数可能不完整，本次未执行；请重新发起完整的工具调用。'
                          '要写入的内容较长时不要一次写完：先写第一部分，再用 edit_file 分段续写。')
ABORTED_CALL_MESSAGE = 'Operation aborted'  # pi agent-loop:520-544 原句
PINNED_CONTEXT_RATIO = 0.6  # 技能正文（常驻内容）可占上下文预算的比例，其余留给对话与输出


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
        self.cache_read_tokens = 0   # pi Usage.cacheRead：命中提示缓存的输入 token
        self.reasoning_tokens = 0    # pi Usage.reasoning：思维链消耗
        self.executed_tools = 0
        self.loaded_skills: set[str] = set()
        self.pinned_chars = 0
        # 工具自报能力不可用的名字（ToolResult.unavailable）：只做 run 级记账，
        # 让 follow-up 策略能区分"能力不在场"与"模型没做"。
        self.unavailable_tools: set[str] = set()
        self.tool_calls: dict[str, int] = {}
        self.tool_errors: dict[str, int] = {}
        # 成功次数：区分"拿到了结果"与"只是尝试过"——实测模型对彻底不可用的工具
        # 连调 2 次失败，按调用次数计会骗过任何以次数为据的策略。
        self.tool_success: dict[str, int] = {}
        self.interventions = 0  # get_follow_up_messages 已注入次数（策略限流依据）
        self.deadline_at: float | None = None  # run 级 deadline 的单调钟截点（provider 重试参考）
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
            cache_read_tokens=self.cache_read_tokens,
            reasoning_tokens=self.reasoning_tokens,
            tool_calls=dict(self.tool_calls),
            tool_errors=dict(self.tool_errors),
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
    """自然停止（STOP/LENGTH 且有正文）：尚未 finalize——_drive 先查 follow_up，
    无排队追问才落终态（pi：agent 会停时先 poll followUp 队列）。"""
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
                 max_context_chars: int = 180_000,
                 max_tool_result_chars: int = 24_000,
                 skills: SkillStore | None = None,
                 resident_skills: Sequence[str] = (),
                 max_pinned_chars: int | None = None,
                 checkpoint_store: CheckpointStore | None = None,
                 compaction: bool = False,
                 compaction_at: float = 0.8,
                 compaction_keep_chars: int = 240_000,  # pi keepRecentTokens=20000 的 3 倍字符当量
                 max_summary_tokens: int | None = None,
                 tool_execution: str = 'parallel',  # pi 默认 parallel（types.ts:267 "Default: parallel"）
                 latent_tools: Sequence[str] = (),
                 tool_policy: ToolPolicy | None = None,
                 skill_tools: Callable[[Any], Sequence[Tool]] | None = None,
                 compose_system: Callable[[str], str] | None = None,
                 ask_user: bool = False,
                 before_tool_call: BeforeToolCall | None = None,
                 after_tool_call: AfterToolCall | None = None,
                 should_stop_after_turn: Callable[[StopContext], bool] | None = None,
                 prepare_next_turn: Callable[[StopContext], 'NextTurn' | None] | None = None,
                 get_follow_up_messages: Callable[[FollowUpContext], Sequence[str]] | None = None):
        self.config = model_config()
        self.provider = provider or OpenAICompatProvider(self.config)
        self.skills = skills
        self.checkpoint_store = checkpoint_store
        self.compaction = compaction
        self.compaction_at = compaction_at
        self.compaction_keep_chars = compaction_keep_chars
        self.tool_execution = tool_execution
        self.before_tool_call = before_tool_call
        self.after_tool_call = after_tool_call
        self.should_stop_after_turn = should_stop_after_turn
        self.prepare_next_turn = prepare_next_turn
        self.get_follow_up_messages = get_follow_up_messages
        self._active_run = False  # pi agent.ts activeRun：同一实例并发 run 互斥
        # pi：maxTokens = min(0.8 × reserveTokens, model.maxTokens)；reserve 按字符预算折算
        reserve_chars = (1.0 - compaction_at) * max_context_chars
        self.max_summary_tokens = max_summary_tokens or max(256, int(reserve_chars * 0.8 / 4))
        self.resident_skills: list[Skill] = []
        if skills is not None:
            for name in resident_skills:
                skill = skills.get(name)
                if skill is None:
                    raise ValueError(f'常驻技能不存在: {name}')
                if not skill.executable:
                    raise ValueError(f'vendor 技能不可常驻: {name}')
                self.resident_skills.append(skill)

        # pinned 预算与上下文预算同源：技能正文是常驻内容，能吃多少由 max_context_chars
        # 决定，不设第二个魔数（此前写死 40k，而技能正文总量已 91k——装载第三个技能被拒）。
        self.max_pinned_chars = (max_pinned_chars if max_pinned_chars is not None
                                 else int(max_context_chars * PINNED_CONTEXT_RATIO))
        all_tools: list[Tool] = list(tools)
        # 技能相关的工具与策略由组合根注入（skill_tools 工厂 / tool_policy）：
        # 内核运行期不 import 能力层——传了 store 但没注入装配函数时，按 skills 层的
        # 默认实现回退（便利路径，惰性导入，不构成模块级耦合）。
        # 技能库为空时不注册 read_skill，也不装配策略：否则会向模型宣称一个没有内容的工具
        # （"不宣称不存在的工具"）。
        if skills is not None and skills.names():
            # 便利路径：未注入装配函数时按 skills 层的默认实现装配（惰性导入，非模块级耦合）。
            # 组合根可以只传 tool_policy / skill_tools 来完全绕开本回退。
            from app.services.agent.skills import SkillPolicy, read_skill_tool
            all_tools.extend(skills.tools() if skill_tools is None else skill_tools(skills))
            if skill_tools is None:
                all_tools.append(read_skill_tool(skills))
            if tool_policy is None:
                tool_policy = SkillPolicy(skills, self.max_pinned_chars)
            if compose_system is None:
                # 默认 system 装配：业务 system → 常驻技能正文 → 按需技能清单
                # （pi 两级注入）。组合根注入 compose_system 时可完全接管。
                resident = tuple(self.resident_skills)
                store = skills

                def compose_system(base: str) -> str:
                    sections = [base] if base else []
                    sections.extend(skill.body for skill in resident if skill.body)
                    listing = store.listing_prompt(exclude=[s.name for s in resident])
                    if listing:
                        sections.append(listing)
                    return '\n\n'.join(sections)
        self.tool_policy: ToolPolicy | None = tool_policy
        self.compose_system: Callable[[str], str] | None = compose_system
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
        self.effective_system = self._compose_system()
        self.temperature = temperature
        self.max_turns = max_turns
        self.deadline_s = deadline_s
        self.max_tool_calls = max_tool_calls
        self.max_context_chars = max_context_chars
        self.max_tool_result_chars = max_tool_result_chars
        chosen = self.config.model if not model or model == 'default' else model
        if chosen not in self.config.models:
            raise BusinessError(20001, '所选模型未配置，请刷新后选择可用模型')
        self.model = chosen

    def _compose_system(self) -> str:
        """system 装配：业务 system → 常驻技能正文 → 按需技能清单（pi 两级注入）。

        「技能正文与清单从哪来」由组合根经 compose_system 注入——内核只知道
        "还有一段附加内容"，不认识技能（依赖方向：runtime 不在运行期 import 能力层）。
        """
        if self.compose_system is None:
            return self.system
        return self.compose_system(self.system)

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
        # run 级可变覆盖（prepare_next_turn 可换模型/温度；pi AgentLoopTurnUpdate）
        model, temperature = self.model, self.temperature
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
                    outcome = await self._run_turn(state, emit, stop_requested, pending_steering,
                                                   model=model, temperature=temperature)
                    # 每个完成的 turn 都落一次快照（含 max_turns 中断态——批次已闭合、可续跑）
                    if self.checkpoint_store is not None:
                        await self.checkpoint_store.save(Checkpoint(
                            run_id=state.run_id, turn=state.turn,
                            messages=[message_to_dict(m) for m in state.messages],
                            prompt_tokens=state.prompt_tokens,
                            completion_tokens=state.completion_tokens,
                            summary=state.summary,
                            read_files=state.read_files,
                            modified_files=state.modified_files,
                            loaded_skills=sorted(state.loaded_skills),
                            pinned_chars=state.pinned_chars,
                            executed_tools=state.executed_tools))
                    if outcome is not None and not isinstance(outcome, _NaturalStop):
                        break  # 终态（_run_turn 内已 finalize）
                    # 轮级钩子紧跟 turn_end（pi agent-loop:252 shouldStopAfterTurn）
                    context = self._stop_context(state)
                    if context is not None:
                        if (self.should_stop_after_turn is not None
                                and self.should_stop_after_turn(context)):
                            state.finalize(StopReason.STOP)
                            break
                        if self.prepare_next_turn is not None:
                            update = self.prepare_next_turn(context)
                            if update is not None:
                                model = update.model or model
                                temperature = (update.temperature
                                               if update.temperature is not None else temperature)
                    # steering poll ②：turn_end 之后（pi agent-loop:257）——有插话就再开一轮
                    steered = pending_steering()
                    for message in steered:
                        state.messages.append(message)
                        emit(state.turn, MESSAGE, {'text': message.text, 'kind': 'steer'})
                    if steered:
                        continue
                    if isinstance(outcome, _NaturalStop):
                        # agent 本会自然停止：followUp 位点（pi agent-loop:261）——
                        # 用户排队的追问优先，其次由策略判断"是否还没做完"
                        follow_ups = channel.drain_follow_ups() if channel is not None else []
                        if not follow_ups and self.get_follow_up_messages is not None:
                            texts = self.get_follow_up_messages(
                                self._follow_up_context(state, outcome.reason)) or ()
                            follow_ups = [UserMessage(text) for text in texts if text]
                            if follow_ups:
                                state.interventions += 1
                        if not follow_ups:
                            state.finalize(outcome.reason)
                            break
                        for message in follow_ups:
                            state.messages.append(message)
                            emit(state.turn, MESSAGE, {'text': message.text, 'kind': 'follow_up'})
        except TimeoutError:
            _close_pending(state, emit, '未执行：运行超时')
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

    def _stop_context(self, state: _RunState) -> StopContext | None:
        """轮级钩子的上下文（pi ShouldStopAfterTurnContext / PrepareNextTurnContext）。"""
        last = next((m for m in reversed(state.messages) if isinstance(m, AssistantMessage)), None)
        if last is None:
            return None
        results = tuple(m for m in state.messages if isinstance(m, ToolResultMessage))
        return StopContext(
            message=last, tool_results=results, stop_reason=last.stop_reason,
            turn=state.turn, executed_tools=state.executed_tools,
            prompt_tokens=state.prompt_tokens, completion_tokens=state.completion_tokens)

    def _follow_up_context(self, state: _RunState, reason: StopReason) -> FollowUpContext:
        """把 run 事实快照给 follow-up 策略：只读、不含任何业务规则。

        文件清单按 pi extractFileOps 从工具调用现算（compaction 后的历史以 state 上的
        清单为准续传），策略据此定位交付物，无需循环逐轮记账。
        """
        last = next((m for m in reversed(state.messages) if isinstance(m, AssistantMessage)), None)
        read_files, modified_files = extract_file_ops(
            state.messages, prior_read=state.read_files, prior_modified=state.modified_files)
        return FollowUpContext(
            messages=tuple(state.messages),
            stop_reason=reason,
            final_text=last.content if last is not None else '',
            turn=state.turn,
            executed_tools=state.executed_tools,
            tool_calls=dict(state.tool_calls),
            tool_errors=dict(state.tool_errors),
            available_tools=frozenset(self.registry.enabled),
            unavailable_tools=frozenset(state.unavailable_tools),
            loaded_skills=frozenset(state.loaded_skills),
            read_files=tuple(sorted(read_files)),
            modified_files=tuple(sorted(modified_files)),
            interventions=state.interventions,
            remaining_s=(max(0.0, state.deadline_at - time.monotonic())
                         if state.deadline_at is not None else None),
        )

    async def _run_turn(self, state: _RunState, emit: Callable, stop_requested: Callable,
                        pending_steering: Callable[[], list[UserMessage]],
                        *, model: str | None = None,
                        temperature: float | None = None) -> StopReason | None:
        """执行一轮：请求 → 流式 → 工具批 → turn_end（pi agent-loop 的 turn 段）。

        返回非 None 表示运行已终态化；`_NaturalStop` 表示本轮无工具调用（agent 本会停止）；
        None 表示继续下一轮。位点顺序照 pi：turn_end 在工具执行**之后**发，
        shouldStopAfterTurn / steering / followUp 由 _drive 在 turn_end 之后依次处理。
        """
        state.turn += 1
        emit(state.turn, TURN_START, {'turn': state.turn})
        await self._maybe_compact(state, emit)  # pi transformContext 位点：下一请求前按需压缩
        # 压缩是长耗时准备，之后补一次 steering poll（pi agent-loop:194-196）——
        # 否则压缩期间到达的插话要么被折进摘要、要么白等一轮。
        for message in pending_steering():
            state.messages.append(message)
            emit(state.turn, MESSAGE, {'text': message.text, 'kind': 'steer'})
        wire, truncated = assemble(
            self.effective_system, state.messages,
            max_chars=self.max_context_chars,
            max_tool_result_chars=self.max_tool_result_chars,
            tools_wire_chars=len(str(self.registry.wire())),
        )
        state.truncated = state.truncated or truncated
        tools_wire = self.registry.wire()
        request = ModelRequest(model or self.model, wire, tools_wire, temperature,
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
                        state.cache_read_tokens += event.usage.cache_read_tokens
                        state.reasoning_tokens += event.usage.reasoning_tokens
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
        used = estimate_context_chars(state.messages, system_chars=len(self.effective_system),
                                      tools_wire_chars=tools_wire_chars)
        if used < self.compaction_at * self.max_context_chars:
            return
        plan = plan_compaction(state.messages, keep_recent_chars=self.compaction_keep_chars,
                               prior_read=state.read_files, prior_modified=state.modified_files,
                               system_chars=len(self.effective_system), tools_wire_chars=tools_wire_chars)
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
        after = estimate_context_chars(new_messages, system_chars=len(self.effective_system),
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
        prepared: list[tuple[ToolCall, 'PreparedCall | None', ToolResult | None]] = []
        for call in calls:
            if stop_requested():
                break
            if self.max_tool_calls is not None and state.executed_tools >= self.max_tool_calls:
                prepared.append((call, None, ToolResult(call.call_id, call.name,
                                                        BUDGET_MESSAGE, is_error=True)))
                continue
            if self.tool_policy is not None:
                blocked = self.tool_policy.intercept(call, state)
                if blocked is not None:
                    prepared.append((call, None, blocked))
                    continue
            outcome = await self.registry.prepare(call, before=self.before_tool_call)
            # 未知工具 / 校验失败 / 钩子阻断 → 立即结果（pi prepareToolCall 的三种短路）；
            # 其余进并发执行。两者位置写反会让被阻断的调用当成待执行项送进去。
            prepared.append((call, None, outcome) if isinstance(outcome, ToolResult)
                            else (call, outcome, None))
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
            done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
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
                self._account_call(state, call, result)
            elif call.call_id in executed:
                result, duration_ms = executed[call.call_id]
                self._account_call(state, call, result)
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

    @staticmethod
    def _account_call(state: _RunState, call: ToolCall, result: ToolResult) -> None:
        state.executed_tools += 1
        state.tool_calls[call.name] = state.tool_calls.get(call.name, 0) + 1
        if result.is_error:
            state.tool_errors[call.name] = state.tool_errors.get(call.name, 0) + 1
        else:
            state.tool_success[call.name] = state.tool_success.get(call.name, 0) + 1

    def _record_tool_result(self, state: _RunState, emit: Callable, call: ToolCall,
                            result: ToolResult, duration_ms: int) -> None:
        state.messages.append(ToolResultMessage(result.call_id, result.name,
                                                result.content, result.is_error, result.pinned))
        # 工具自报的能力不可用：只做 run 级记账（供 follow-up 策略判断），不触发续跑。
        state.unavailable_tools.update(result.unavailable)
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
        if self.tool_policy is not None:
            blocked = self.tool_policy.intercept(call, state)
            if blocked is not None:
                return blocked, 0
        if self.max_tool_calls is not None and state.executed_tools >= self.max_tool_calls:
            return ToolResult(call.call_id, call.name, BUDGET_MESSAGE, is_error=True), 0
        tool_started = time.monotonic()
        result = await self.registry.dispatch(
            call, before=self.before_tool_call, after=self.after_tool_call)
        if self.tool_policy is not None:
            result = self.tool_policy.settle(call, result, state)
        self._account_call(state, call, result)
        return result, int((time.monotonic() - tool_started) * 1000)
