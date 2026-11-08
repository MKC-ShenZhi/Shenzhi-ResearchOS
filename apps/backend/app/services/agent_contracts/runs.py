"""Platform execution attempts; runtime RunResult remains the sole result type."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .budgets import BudgetLimits, UsageReport

if TYPE_CHECKING:
    from app.services.agent.execution.types import RunResult


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


@dataclass(frozen=True)
class RunRecord:
    """One persisted attempt snapshot; future Task Manager owns transitions."""
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


@dataclass(frozen=True)
class ExecutionReport:
    run_id: str
    task_id: str
    status: RunStatus
    result: RunResult | None = None
    usage: UsageReport = field(default_factory=UsageReport)
    error_code: str | None = None
    error_message: str | None = None


def report_from_result(request: RunRequest, result: RunResult) -> ExecutionReport:
    """Map one completed runtime attempt without altering its terminal semantics."""
    status = {
        'done': RunStatus.COMPLETED,
        'failed': RunStatus.FAILED,
        'stopped': RunStatus.CANCELLED,
        'timeout': RunStatus.TIMED_OUT,
        'awaiting_input': RunStatus.AWAITING_INPUT,
    }[result.status]
    error: Any = result.error
    return ExecutionReport(
        run_id=request.run_id, task_id=request.task_id, status=status,
        result=result,
        usage=UsageReport(prompt_tokens=result.prompt_tokens,
                          completion_tokens=result.completion_tokens,
                          duration_ms=result.duration_ms),
        error_code=str(error.code) if error else None,
        error_message=str(error.message) if error else None,
    )
