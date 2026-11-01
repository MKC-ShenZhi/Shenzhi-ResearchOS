"""Offline sync of displayable knowledge papers into the home-feed pool.

The home feed never calls the knowledge base at request time. This job walks
every venue for one year through the browse API, keeps only papers a home card
can actually show, and replaces that year's pool in one transaction.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.schemas.knowledge import PaperBrowseRequest, PaperSearchResult
from app.services.home_feed.rules import admit, displayable_image_id
from app.services.knowledge.service import KnowledgeService, KnowledgeServiceError

__all__ = ['DiscoveryPoolSync', 'PoolSyncError', 'PoolSyncResult', 'displayable_image_id', 'pool_row']

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
CONCURRENCY = 4
PAGE_ATTEMPTS = 3
WRITE_CHUNK = 500
# A sync that would drop more than half of a year's pool is far more likely an
# upstream outage or contract drift than real deletions, so it is refused.
MIN_RETAINED_RATIO = 0.5


class PoolSyncError(RuntimeError):
    """The sync was refused or incomplete; the existing pool is left untouched."""


def pool_row(paper: PaperSearchResult, venue: str, year: int) -> tuple[dict[str, Any] | None, str | None]:
    """Return the cleaned row, or the reason a home card could not show this paper (rule B)."""
    admitted, reason = admit({
        'id': paper.id, 'title': paper.title, 'abstract': paper.abstract, 'authors': paper.authors,
        'year': paper.year, 'venue': venue, 'image_id': paper.image_id,
        'keywords': paper.keywords, 'subjects': paper.subjects,
    }, year=year)
    if admitted is None:
        return None, reason
    return {
        'paper_id': admitted.id, 'title': admitted.title, 'abstract': admitted.abstract,
        'authors': admitted.authors, 'year': year, 'venue': venue, 'image_id': admitted.image_id,
        'subjects': admitted.subjects, 'keywords': admitted.keywords,
        'primary_subject': (paper.primary_subject or '').strip() or None,
    }, None


@dataclass
class PoolSyncResult:
    year: int
    venues: int = 0
    fetched: int = 0
    accepted: int = 0
    rejected: Counter = field(default_factory=Counter)
    by_venue: Counter = field(default_factory=Counter)
    previous: int | None = None
    removed: int | None = None
    synced_at: datetime | None = None

    def summary(self) -> dict[str, Any]:
        return {
            'year': self.year, 'venues': self.venues, 'fetched': self.fetched,
            'accepted': self.accepted, 'rejected': dict(sorted(self.rejected.items())),
            'by_venue': dict(self.by_venue.most_common()),
            'previous': self.previous, 'removed': self.removed,
            'synced_at': self.synced_at.isoformat() if self.synced_at else None,
        }


class DiscoveryPoolSync:
    def __init__(self, knowledge: KnowledgeService | None = None, *, retry_delay: float = 1.0):
        self.knowledge = knowledge or KnowledgeService()
        self.retry_delay = retry_delay

    async def collect(self, year: int) -> tuple[list[dict[str, Any]], PoolSyncResult]:
        result = PoolSyncResult(year=year)
        venues = [venue.name for venue in (await self.knowledge.conferences()).items if year in venue.years]
        if not venues:
            raise PoolSyncError(f'No knowledge venue lists papers for {year}')
        result.venues = len(venues)
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def fetch(venue: str, offset: int):
            async with semaphore:
                for attempt in range(1, PAGE_ATTEMPTS + 1):
                    try:
                        return await self.knowledge.browse_papers(PaperBrowseRequest(
                            conference=venue, year=year, limit=PAGE_SIZE, offset=offset,
                        ))
                    except KnowledgeServiceError:
                        if attempt == PAGE_ATTEMPTS:
                            raise
                        await asyncio.sleep(self.retry_delay * attempt)

        try:
            first_pages = await asyncio.gather(*(fetch(venue, 0) for venue in venues))
            rest = [(venue, offset) for venue, page in zip(venues, first_pages)
                    for offset in range(PAGE_SIZE, page.total, PAGE_SIZE)]
            later_pages = await asyncio.gather(*(fetch(venue, offset) for venue, offset in rest))
        except KnowledgeServiceError as error:
            # One missing page would silently shrink the pool, so the whole run fails.
            raise PoolSyncError('Knowledge browse failed; the existing pool is kept') from error

        rows: dict[str, dict[str, Any]] = {}
        pages = list(zip(venues, first_pages)) + [(venue, page) for (venue, _), page in zip(rest, later_pages)]
        for venue, page in pages:
            for paper in page.results:
                result.fetched += 1
                row, reason = pool_row(paper, venue, year)
                if reason is None and paper.id in rows:
                    reason = 'duplicate'
                if reason is not None:
                    result.rejected[reason] += 1
                    continue
                rows[paper.id] = row
                result.by_venue[venue] += 1
        result.accepted = len(rows)
        return list(rows.values()), result

    async def sync(self, year: int, *, dry_run: bool = False) -> PoolSyncResult:
        rows, result = await self.collect(year)
        async with session_scope() as session:
            result.previous = int(await session.scalar(
                select(func.count()).select_from(DiscoveryPoolPaperRow).where(DiscoveryPoolPaperRow.year == year),
            ) or 0)
            if not rows or (result.previous and len(rows) < result.previous * MIN_RETAINED_RATIO):
                raise PoolSyncError(
                    f'Refusing to replace {result.previous} pool papers with {len(rows)} for {year}',
                )
            if dry_run:
                return result
            synced_at = utc_now()
            for start in range(0, len(rows), WRITE_CHUNK):
                statement = insert(DiscoveryPoolPaperRow).values([
                    {**row, 'synced_at': synced_at} for row in rows[start:start + WRITE_CHUNK]
                ])
                await session.execute(statement.on_conflict_do_update(
                    index_elements=[DiscoveryPoolPaperRow.paper_id],
                    set_={column: statement.excluded[column] for column in (
                        'title', 'abstract', 'authors', 'year', 'venue', 'image_id',
                        'subjects', 'keywords', 'primary_subject', 'synced_at',
                    )},
                ))
            removed = await session.execute(delete(DiscoveryPoolPaperRow).where(
                DiscoveryPoolPaperRow.year == year, DiscoveryPoolPaperRow.synced_at < synced_at,
            ))
            result.removed = int(removed.rowcount or 0)
            result.synced_at = synced_at
        return result
