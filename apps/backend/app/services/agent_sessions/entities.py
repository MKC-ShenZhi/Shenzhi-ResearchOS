"""In-process Agent session entities shared by memory and PostgreSQL repositories."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentTurn:
    id: str
    session_id: str
    user_content: str
    settings: dict[str, Any]
    assistant_content: str = ''
    reasoning: str = ''
    process: list[dict[str, Any]] = field(default_factory=list)
    steers: list[dict[str, Any]] = field(default_factory=list)
    report: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    question: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    stopped: bool = False
    stop_reason: str | None = None
    status: str = 'running'
    usage: dict[str, Any] = field(default_factory=dict)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def public(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'user_content': self.user_content,
            'assistant_content': self.assistant_content,
            'reasoning': self.reasoning,
            'process': self.process,
            'steers': self.steers,
            'report': self.report,
            'sources': self.sources,
            'question': self.question,
            'warnings': self.warnings,
            'error': self.error,
            'stopped': self.stopped,
            'stop_reason': self.stop_reason,
            'status': self.status,
            'settings': self.settings,
            'usage': self.usage,
            'created_at': self.created_at,
            'completed_at': self.completed_at,
        }


@dataclass
class AgentSession:
    id: str
    owner: str
    title: str
    settings: dict[str, Any] = field(default_factory=dict)
    branched_from: str | None = None
    import_key: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turns: list[AgentTurn] = field(default_factory=list)

    @property
    def runtime_history(self) -> list[dict[str, Any]]:
        return self.turns[-1].transcript if self.turns else []

    def summary(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'settings': self.settings,
            'branched_from': self.branched_from,
        }

    def public(self) -> dict[str, Any]:
        return {**self.summary(), 'turns': [turn.public() for turn in self.turns]}
