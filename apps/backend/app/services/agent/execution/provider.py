"""Provider request, event and protocol contracts used by the Agent runtime."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from app.services.agent.execution.types import StopReason, ToolCall

MAX_OUTPUT_TOKENS = 32768

@dataclass(frozen=True)
class ModelRequest:
    model: str
    messages: list[dict]
    tools: list[dict] = field(default_factory=list)
    temperature: float | None = None
    max_tokens: int = MAX_OUTPUT_TOKENS
    deadline_at: float | None = None  # time.monotonic() 截止点；剩余不足时不再重试


@dataclass(frozen=True)
class Usage:
    """一次请求的用量（pi ai/types.ts Usage 的字段子集）。

    只保留被消费的 input/output 两项；cache_read / reasoning / cost 等上游
    附加字段没有下游读者，就不解析进契约——需要时由业务层自己读原始响应。
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True)
class ToolCallEvent:
    call: ToolCall


@dataclass(frozen=True)
class Finish:
    stop_reason: StopReason
    usage: Usage | None = None
    # pi：未知/被审核的 finish_reason 映射为 error，并保留上游说明
    # （openai-completions.ts:1550-1574 的 errorMessage），
    # 否则"被内容审核截断"会伪装成"模型正常说完"。原始取值只进日志，不进契约。
    error_message: str = ''


ProviderEvent = TextDelta | ReasoningDelta | ToolCallEvent | Finish


class ModelProvider(Protocol):
    """stream 必须是 async 生成器（runtime 用 aclosing 确定性关闭连接）。"""

    def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]: ...


