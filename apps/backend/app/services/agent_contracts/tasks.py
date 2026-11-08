"""Task identity and lifecycle; a Task is neither a Session nor a Turn."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class TaskStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    PAUSED = 'paused'
    AWAITING_INPUT = 'awaiting_input'
    CANCELLING = 'cancelling'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


@dataclass(frozen=True)
class TaskSubmission:
    owner_id: str  # Existing identity owner, e.g. user:<id> / anon:<id>.
    prompt: str
    session_id: str | None = None
    input_ref: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    submission: TaskSubmission
    status: TaskStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancel_requested: bool = False
    current_run_id: str | None = None

    @property
    def owner_id(self) -> str:
        return self.submission.owner_id

    @property
    def session_id(self) -> str | None:
        return self.submission.session_id
