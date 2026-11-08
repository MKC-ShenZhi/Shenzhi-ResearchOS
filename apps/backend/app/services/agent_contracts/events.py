"""Platform envelope around the existing runtime event, not a second event source."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.execution.types import AgentEvent


@dataclass(frozen=True)
class PlatformEvent:
    task_id: str
    run_id: str
    runtime_event: AgentEvent
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def sequence(self) -> int:
        return self.runtime_event.seq

    @property
    def name(self) -> str:
        return self.runtime_event.name
