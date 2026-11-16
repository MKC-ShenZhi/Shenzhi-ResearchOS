"""Small process-local caches for Knowledge service results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Generic, TypeVar

from app.schemas.knowledge import PaperDetail, ScholarProfilePage
from app.schemas.nsfc_project import ProjectList


PAPER_DETAIL_TTL_SECONDS = 10 * 60
PAPER_DETAIL_CACHE_MAX_ENTRIES = 1024
CacheKey = TypeVar('CacheKey')
CacheValue = TypeVar('CacheValue')


@dataclass(frozen=True)
class _CacheEntry(Generic[CacheValue]):
    value: CacheValue
    expires_at: float


class KnowledgeTTLCache(Generic[CacheKey, CacheValue]):
    """Bounded in-memory TTL cache shared by services in one process."""

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = monotonic,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._entries: dict[CacheKey, _CacheEntry[CacheValue]] = {}

    def get(self, key: CacheKey) -> CacheValue | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self.clock():
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: CacheKey, value: CacheValue) -> None:
        now = self.clock()
        self._prune_expired(now)
        self._entries.pop(key, None)
        if len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = _CacheEntry(
            value=value,
            expires_at=now + self.ttl_seconds,
        )

    def clear(self) -> None:
        self._entries.clear()

    def _prune_expired(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for key in expired:
            self._entries.pop(key, None)


class PaperDetailTTLCache(KnowledgeTTLCache[str, PaperDetail]):
    def __init__(
        self,
        *,
        ttl_seconds: float = PAPER_DETAIL_TTL_SECONDS,
        max_entries: int = PAPER_DETAIL_CACHE_MAX_ENTRIES,
        clock: Callable[[], float] = monotonic,
    ):
        super().__init__(ttl_seconds=ttl_seconds, max_entries=max_entries, clock=clock)


shared_paper_detail_cache = PaperDetailTTLCache()
ScholarBrowseCache = KnowledgeTTLCache[tuple[int, int], ScholarProfilePage]
shared_scholar_browse_cache = ScholarBrowseCache(ttl_seconds=5 * 60, max_entries=128)
ProjectFirstPageCache = KnowledgeTTLCache[int, ProjectList]
shared_project_first_page_cache = ProjectFirstPageCache(ttl_seconds=5 * 60, max_entries=50)
