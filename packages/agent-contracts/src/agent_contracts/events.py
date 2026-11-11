"""JSON-compatible, replayable Agent execution event envelope."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PlatformEvent:
    task_id: str
    run_id: str
    seq: int
    turn: int
    name: str
    data: dict[str, Any]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_key(self) -> tuple[str, int]:
        return (self.run_id, self.seq)

    @property
    def sequence(self) -> int:
        return self.seq
