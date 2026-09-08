"""In-process Chat session/message entities shared by Memory and Postgres repositories."""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    id: str
    session_id: str
    question: str
    settings: dict[str, Any]
    attachment_context: str = ''
    warnings: list[str] = field(default_factory=list)
    content: str = ''
    reasoning: str = ''
    status: str = 'streaming'
    references: list[dict] = field(default_factory=list)
    followups: list[str] = field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None
    events: list[tuple[str, dict]] = field(default_factory=list)
    task: asyncio.Task | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    subscribers: int = 0
    stop_requested: bool = False
    stream_request_id: str | None = None
    stop_request_id: str | None = None

    def emit(self, event: str, data: dict) -> None:
        self.events.append((event, data))
        self.changed.set()

    def public(self) -> dict:
        data = {"last_event_id": str(len(self.events)), **{k: getattr(self, k) for k in (
            'id', 'question', 'content', 'reasoning', 'status', 'references',
            'followups', 'duration_ms', 'error', 'warnings',
        )}}
        grounding = self.settings.get('knowledge_grounding')
        if grounding in {'grounded', 'unavailable', 'unverified'}:
            data['knowledge_grounding'] = grounding
        return data


@dataclass
class Session:
    id: str
    owner: str
    title: str
    settings: dict[str, Any]
    favorite: bool = False
    updated_at: float = field(default_factory=time.time)
    messages: list[Message] = field(default_factory=list)

    def public(self, detail: bool = False) -> dict:
        data = {'id': self.id, 'title': self.title, 'favorite': self.favorite,
                'updated_at': self.updated_at, **self.settings}
        if detail:
            data['messages'] = [item.public() for item in self.messages]
        return data
