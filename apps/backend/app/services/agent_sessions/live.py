"""Single-process run ownership and replay, independent of HTTP subscribers."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class LiveRun:
    session_id: str
    owner: str
    turn_id: str
    events: list[tuple[str, dict]] = field(default_factory=list)
    done: bool = False
    task: asyncio.Task | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)


_live: dict[str, LiveRun] = {}
_tasks: set[asyncio.Task] = set()


def get_live(session_id: str, owner: str) -> LiveRun | None:
    live = _live.get(session_id)
    return live if live is not None and live.owner == owner else None


def register(live: LiveRun) -> None:
    _live[live.session_id] = live


def append(live: LiveRun, name: str, data: dict) -> None:
    live.events.append((name, data))
    changed, live.changed = live.changed, asyncio.Event()
    changed.set()


def finish(live: LiveRun) -> None:
    live.done = True
    live.changed.set()

    def expire() -> None:
        if _live.get(live.session_id) is live:
            del _live[live.session_id]

    asyncio.get_running_loop().call_later(600, expire)


async def subscribe(live: LiveRun, after: int = 0) -> AsyncIterator[tuple[int, str, dict] | None]:
    index = after
    while True:
        # Capture the notification before checking the buffer: an append between
        # draining and waiting must not strand this subscriber until its heartbeat.
        changed = live.changed
        while index < len(live.events):
            name, data = live.events[index]
            yield index, name, data
            index += 1
        if live.done:
            return
        try:
            await asyncio.wait_for(changed.wait(), timeout=15)
        except TimeoutError:
            yield None
