"""Agent 基座核心类型：消息、工具调用、事件与运行结果。

全部是纯数据、可 JSON 序列化 —— 消息轨迹（RunResult.messages）从第一天就是
可持久化、可恢复的：任何停止路径下 tool 调用都有对应结果（runtime 的批次
闭合），transcript 永远合法，可原样作为下次 run 的 history。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union

from app.core.errors import BusinessError


class StopReason(str, Enum):
    STOP = 'stop'
    LENGTH = 'length'
    TOOL_CALLS = 'tool_calls'
    MAX_TURNS = 'max_turns'
    ERROR = 'error'
    CANCELLED = 'cancelled'
    TIMEOUT = 'timeout'
    # 向用户提问后干净停轮（制品是问题本身，不是答案）：用户回答作为下一条消息回传。
    AWAITING_INPUT = 'awaiting_input'


# 事件名常量；seq 是 run 内排序号。断线重放由业务层事件日志承载
#（chat 的 Message.events + Last-Event-ID 是现成先例），基座不内建。
RUN_START = 'run_start'
TURN_START = 'turn_start'
MESSAGE = 'message'  # run 中注入的 steer / system 消息（pi message_start/end 的单事件对应）
DELTA = 'delta'
TOOL_CALL = 'tool_call'
TOOL_END = 'tool_end'
TURN_END = 'turn_end'
COMPACTION = 'compaction'
RUN_END = 'run_end'


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    # 已解析的参数对象（pi `ToolCall.arguments: Record<string, any>` 同型）。
    # 解析在 AI 层完成且绝不抛错（json_repair.parse_streaming_json 的阶梯），因此：
    # ① 发回上游的 function.arguments 永远是合法 JSON（拼 JSON 文本的路径已不存在）；
    # ② 参数仍是"未校验"的——校验发生在执行前（ToolRegistry.prepare 过 pydantic）。
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    content: str  # 喂给模型的文本
    is_error: bool = False
    # 非 None：最终制品直出 RunResult.output，不经模型转述（引用编号零失真）
    terminal: Any = None
    # pi addedToolNames（types.ts:370）：此结果起可用的工具名（从 latent 集合启用，下一轮生效）
    added_tool_names: tuple[str, ...] = ()
    # 指令性内容（如技能说明）：随 ToolResultMessage 落账后豁免上下文截断。
    # 通用属性——任何工具（或 policy 钩子）都能声明，不与具体工具绑定。
    pinned: bool = False


@dataclass
class UserMessage:
    text: str


@dataclass
class AssistantMessage:
    content: str = ''
    reasoning: str = ''
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: StopReason = StopReason.STOP
    # 该次请求的用量（prompt+completion tokens）：pi 把 usage 挂最终消息
    # （ai/types.ts），compaction 据此优先用真实用量估算上下文占用。
    usage_tokens: int = 0


@dataclass
class ToolResultMessage:
    call_id: str
    name: str
    content: str
    is_error: bool = False
    pinned: bool = False  # 指令性内容（如 read_skill 结果）豁免上下文截断


AgentMessage = Union[UserMessage, AssistantMessage, ToolResultMessage]


# ---- 运行控制契约（pi 把全部契约集中在 types.ts；此处同构） ----


class RunChannel:
    """运行中插话通道（pi steer 队列的线程安全 Python 版）。

    steer：下一个模型请求前注入（工具批不会被跳过）——"运行中插话"。
    线程安全靠 asyncio 单线程事件循环保证；跨线程调用方请用 loop.call_soon_threadsafe。
    """

    def __init__(self) -> None:
        self._steer: list[UserMessage] = []

    def steer(self, text: str) -> None:
        self._steer.append(UserMessage(text))

    def drain_steering(self) -> list[UserMessage]:
        drained, self._steer = self._steer, []
        return drained

    def has_pending(self) -> bool:
        return bool(self._steer)


@dataclass(frozen=True)
class AgentEvent:
    seq: int
    turn: int
    name: str
    data: dict[str, Any]


@dataclass
class RunResult:
    stop_reason: StopReason = StopReason.ERROR
    messages: list[AgentMessage] = field(default_factory=list)
    final_text: str = ''
    final_reasoning: str = ''
    output: Any = None  # terminal 工具直出的结构化制品
    turns: int = 0
    duration_ms: int = 0
    error: BusinessError | None = None
    truncated: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def status(self) -> str:
        return {
            StopReason.STOP: 'done',
            StopReason.LENGTH: 'done',
            StopReason.ERROR: 'failed',
            StopReason.CANCELLED: 'stopped',
            StopReason.TIMEOUT: 'timeout',
            StopReason.MAX_TURNS: 'failed',
            StopReason.TOOL_CALLS: 'failed',  # 不应作为终态出现
            StopReason.AWAITING_INPUT: 'awaiting_input',
        }[self.stop_reason]

    @property
    def question(self) -> dict[str, Any] | None:
        """等待用户回答时的问题制品（`output.kind == 'question'`），否则 None。

        提问走的是基座既有的 terminal 直出通道——问题本身就是这一轮的制品，
        与 deep-research 的报告直出同一条路径，因此引用/选项不会经模型转述而失真。
        """
        output = self.output
        if isinstance(output, dict) and output.get('kind') == 'question':
            return output
        return None


def message_to_dict(message: AgentMessage) -> dict[str, Any]:
    """消息编解码：持久化 / 跨进程恢复的唯一格式。"""
    if isinstance(message, UserMessage):
        return {'kind': 'user', 'text': message.text}
    if isinstance(message, AssistantMessage):
        return {
            'kind': 'assistant',
            'content': message.content,
            'reasoning': message.reasoning,
            'tool_calls': [
                {'call_id': call.call_id, 'name': call.name, 'arguments': call.arguments}
                for call in message.tool_calls
            ],
            'stop_reason': message.stop_reason.value,
            'usage_tokens': message.usage_tokens,
        }
    return {
        'kind': 'tool',
        'call_id': message.call_id,
        'name': message.name,
        'content': message.content,
        'is_error': message.is_error,
        'pinned': message.pinned,
    }


def _decoded_arguments(raw: Any) -> dict[str, Any]:
    """历史消息里的参数容错解码：对象直接用；文本（旧格式）按同一阶梯解析。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        from app.services.agent.json_repair import parse_streaming_json
        parsed = parse_streaming_json(raw)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def message_from_dict(data: dict[str, Any]) -> AgentMessage:
    kind = data.get('kind')
    if kind == 'user':
        return UserMessage(text=str(data.get('text', '')))
    if kind == 'assistant':
        calls = tuple(
            ToolCall(call_id=str(item.get('call_id', '')), name=str(item.get('name', '')),
                     arguments=_decoded_arguments(item.get('arguments')))
            for item in data.get('tool_calls', []) if isinstance(item, dict)
        )
        return AssistantMessage(
            content=str(data.get('content', '')),
            reasoning=str(data.get('reasoning', '')),
            tool_calls=calls,
            stop_reason=StopReason(data.get('stop_reason', 'stop')),
            usage_tokens=int(data.get('usage_tokens', 0) or 0),
        )
    if kind == 'tool':
        return ToolResultMessage(
            call_id=str(data.get('call_id', '')),
            name=str(data.get('name', '')),
            content=str(data.get('content', '')),
            is_error=bool(data.get('is_error', False)),
            pinned=bool(data.get('pinned', False)),
        )
    raise ValueError(f'未知消息类型: {kind!r}')
