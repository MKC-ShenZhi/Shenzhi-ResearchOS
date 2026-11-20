"""JSON-compatible Run requests and reports shared across service processes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .budgets import BudgetLimits, UsageReport


class RunStatus(StrEnum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    TIMED_OUT = 'timed_out'
    AWAITING_INPUT = 'awaiting_input'


@dataclass(frozen=True)
class RunRequest:
    run_id: str
    task_id: str
    owner_id: str
    prompt: str
    session_id: str | None = None
    mode: str = 'fast'
    model: str | None = None
    workspace_id: str | None = None
    skills: tuple[str, ...] = ()
    budget: BudgetLimits = field(default_factory=BudgetLimits)
    input_ref: str | None = None
    turn_id: str | None = None
    history: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if (self.session_id is None) != (self.turn_id is None):
            raise ValueError('session_id and turn_id must be provided together')


@dataclass(frozen=True)
class RunRecord:
    request: RunRequest
    attempt: int
    status: RunStatus = RunStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.attempt < 1:
            raise ValueError('attempt must start at one')

    @property
    def task_id(self) -> str:
        return self.request.task_id


@dataclass(frozen=True)
class ExecutionReport:
    """Final outcome with a JSON-compatible result payload, independent of Runtime."""
    run_id: str
    task_id: str
    status: RunStatus
    result: dict[str, Any] | None = None
    usage: UsageReport = field(default_factory=UsageReport)
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.status in (RunStatus.PENDING, RunStatus.RUNNING):
            raise ValueError('execution report requires a final run status')
