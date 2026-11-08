"""Authorized limits and measured usage, without invented monetary accounting."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetLimits:
    max_duration_s: float | None = None
    max_tool_calls: int | None = None
    max_model_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_duration_s is not None and self.max_duration_s <= 0:
            raise ValueError('max_duration_s must be positive')
        if self.max_tool_calls is not None and self.max_tool_calls < 0:
            raise ValueError('max_tool_calls cannot be negative')
        if self.max_model_tokens is not None and self.max_model_tokens < 0:
            raise ValueError('max_model_tokens cannot be negative')


@dataclass(frozen=True)
class UsageReport:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tool_calls: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        values = (self.prompt_tokens, self.completion_tokens, self.tool_calls, self.duration_ms)
        if any(value is not None and value < 0 for value in values):
            raise ValueError('usage values cannot be negative')

    @property
    def model_tokens(self) -> int | None:
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens
