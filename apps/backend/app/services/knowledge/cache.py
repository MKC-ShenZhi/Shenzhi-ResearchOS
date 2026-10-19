"""Small process-local caches for Knowledge service results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from app.schemas.knowledge import PaperDetail


PAPER_DETAIL_TTL_SECONDS = 10 * 60
PAPER_DETAIL_CACHE_MAX_ENTRIES = 1024


@dataclass(frozen=True)
class _PaperDetailCacheEntry:
    value: PaperDetail
    expires_at: float


class PaperDetailTTLCache:
    """Bounded in-memory TTL cache shared by services in one process."""

    def __init__(
        self,
        *,
        ttl_seconds: float = PAPER_DETAIL_TTL_SECONDS,
        max_entries: int = PAPER_DETAIL_CACHE_MAX_ENTRIES,
        clock: Callable[[], float] = monotonic,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._entries: dict[str, _PaperDetailCacheEntry] = {}

    def get(self, paper_id: str) -> PaperDetail | None:
        entry = self._entries.get(paper_id)
        if entry is None:
            return None
        if entry.expires_at <= self.clock():
            self._entries.pop(paper_id, None)
            return None
        return entry.value

    def set(self, paper_id: str, value: PaperDetail) -> None:
        now = self.clock()
        self._prune_expired(now)
        self._entries.pop(paper_id, None)
        if len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[paper_id] = _PaperDetailCacheEntry(
            value=value,
            expires_at=now + self.ttl_seconds,
        )

    def clear(self) -> None:
        self._entries.clear()

    def _prune_expired(self, now: float) -> None:
        expired = [
            paper_id
            for paper_id, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for paper_id in expired:
            self._entries.pop(paper_id, None)


shared_paper_detail_cache = PaperDetailTTLCache()
