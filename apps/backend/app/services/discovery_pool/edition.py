"""Build the shared daily edition (the ``daily`` home source) from the paper pool.

Rule A. Each Shanghai day gets one fixed list of EDITION_SIZE pool papers,
stored in ``home_daily_editions``: the least recently shown papers first,
ties broken by a per-day hash, so the whole pool is cycled through before any
paper repeats and a re-run on the same day yields the same edition. Within
papers last shown on the same day no venue exceeds MAX_VENUE_SHARE and no
primary subject exceeds MAX_SUBJECT_SHARE of the edition; freshness still
outranks balance, so a one-venue tier fills the edition rather than leaving
gaps. Rule B (``home_feed.rules.admit``) is applied to every pool paper.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from itertools import groupby
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.home_daily_edition import HomeDailyEditionRow
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.schemas.discovery import DiscoveryPaper
from app.services.discovery import edition_id
from app.services.home_feed.composer import spread_venues
from app.services.home_feed.config import DAILY_LIMIT
from app.services.home_feed.rules import admit

EDITION_SIZE = DAILY_LIMIT
HISTORY_DAYS = 120
MAX_VENUE_SHARE = 0.25
MAX_SUBJECT_SHARE = 0.05


class EditionError(RuntimeError):
    """No edition could be built; the feed keeps serving its other sources."""


@dataclass
class EditionResult:
    edition_date: date
    edition_id: str
    papers: list[DiscoveryPaper]
    pool_size: int = 0
    rejected: Counter = field(default_factory=Counter)
    pool_year: int | None = None
    history_days: int = 0
    repeats: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            'date': self.edition_date.isoformat(), 'edition_id': self.edition_id,
            'size': len(self.papers),
            'venues': dict(Counter(paper.venue for paper in self.papers).most_common()),
            'pool_year': self.pool_year, 'pool_size': self.pool_size, 'rejected': dict(self.rejected),
            'history_days': self.history_days, 'repeats_within_history': self.repeats,
        }


def _shuffle_key(edition_date: date, paper_id: str) -> bytes:
    return hashlib.sha256(f'{edition_date.isoformat()}:{paper_id}'.encode('utf-8')).digest()


class DailyEditionBuilder:
    async def _inputs(self, edition_date: date, year: int | None):
        async with session_scope() as session:
            pool_year = year or await session.scalar(select(func.max(DiscoveryPoolPaperRow.year)))
            pool = [] if pool_year is None else list(await session.scalars(select(DiscoveryPoolPaperRow).where(
                DiscoveryPoolPaperRow.year == pool_year,
            )))
            history = list(await session.execute(select(
                HomeDailyEditionRow.edition_date,
                func.jsonb_path_query_array(
                    HomeDailyEditionRow.payload, literal_column("'$[*].id'::jsonpath"), type_=JSONB,
                ),
            ).where(
                HomeDailyEditionRow.edition_date >= edition_date - timedelta(days=HISTORY_DAYS),
                HomeDailyEditionRow.edition_date < edition_date,
            )))
        last_shown: dict[str, date] = {}
        for shown_on, ids in history:
            for paper_id in ids if isinstance(ids, list) else []:
                if isinstance(paper_id, str) and shown_on > last_shown.get(paper_id, date.min):
                    last_shown[paper_id] = shown_on
        return pool_year, pool, last_shown, len(history)

    async def build(self, edition_date: date, *, size: int = EDITION_SIZE, year: int | None = None) -> EditionResult:
        """Draw from the given pool year, by default the newest one synced."""
        pool_year, pool, last_shown, history_days = await self._inputs(edition_date, year)
        rejected: Counter = Counter()
        candidates: list[tuple[DiscoveryPaper, str | None]] = []
        for row in pool:
            paper, reason = admit(row.paper_fields(), year=pool_year)
            if paper is None:
                rejected[reason] += 1
            else:
                candidates.append((paper, row.primary_subject))
        if not candidates:
            raise EditionError('The discovery pool is empty; run `sync` first')

        candidates.sort(key=lambda item: (last_shown.get(item[0].id, date.min), _shuffle_key(edition_date, item[0].id)))
        chosen: list[DiscoveryPaper] = []
        chosen_ids: set[str] = set()
        venues: Counter = Counter()
        subjects: Counter = Counter()
        venue_cap = max(1, int(size * MAX_VENUE_SHARE))
        subject_cap = max(1, int(size * MAX_SUBJECT_SHARE))

        def take(tier: list[tuple[DiscoveryPaper, str | None]], *, capped: bool) -> None:
            for paper, subject in tier:
                if len(chosen) >= size:
                    return
                if paper.id in chosen_ids:
                    continue
                if capped and (venues[paper.venue] >= venue_cap or (subject and subjects[subject] >= subject_cap)):
                    continue
                chosen.append(paper)
                chosen_ids.add(paper.id)
                venues[paper.venue] += 1
                if subject:
                    subjects[subject] += 1

        # Balance only chooses among papers last shown on the same day.
        for _, tier in groupby(candidates, key=lambda item: last_shown.get(item[0].id, date.min)):
            tier = list(tier)
            take(tier, capped=True)
            take(tier, capped=False)
            if len(chosen) >= size:
                break

        papers = spread_venues(chosen)
        return EditionResult(
            edition_date=edition_date, edition_id=edition_id(edition_date, papers), papers=papers,
            pool_size=len(pool), rejected=rejected, pool_year=pool_year, history_days=history_days,
            repeats=sum(paper.id in last_shown for paper in papers),
        )

    async def publish(self, edition_date: date, *, size: int = EDITION_SIZE, year: int | None = None) -> EditionResult:
        result = await self.build(edition_date, size=size, year=year)
        payload = [paper.model_dump(mode='json') for paper in result.papers]
        async with session_scope() as session:
            statement = insert(HomeDailyEditionRow).values(
                edition_date=edition_date, payload=payload, created_at=utc_now(),
            )
            await session.execute(statement.on_conflict_do_update(
                index_elements=[HomeDailyEditionRow.edition_date],
                set_={'payload': statement.excluded.payload, 'created_at': statement.excluded.created_at},
            ))
        return result

    @staticmethod
    async def purge(today: date) -> int:
        """Delete editions older than the history window; nothing reads them any more."""
        async with session_scope() as session:
            result = await session.execute(delete(HomeDailyEditionRow).where(
                HomeDailyEditionRow.edition_date < today - timedelta(days=HISTORY_DAYS),
            ))
            return int(result.rowcount or 0)
