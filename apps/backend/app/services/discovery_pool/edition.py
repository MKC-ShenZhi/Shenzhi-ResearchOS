"""Build the shared daily home edition from the paper pool.

Each Shanghai day gets one fixed list of EDITION_SIZE papers, stored in
``daily_recommendations`` and served unchanged to everyone that day:

- curated: the packaged hand-picked papers (static thumbnails), rotated so each
  returns roughly every five days;
- popular: papers with platform likes/collections, at most once a week each;
- explore: the rest of the pool, least recently shown first.

Every choice is ordered by (last shown, per-day hash), so a re-run on the same
day with the same inputs yields the same edition, and the pool is cycled
through before any paper repeats. Among equally fresh papers no venue exceeds
MAX_VENUE_SHARE of the edition, and no screen shows one venue more than
VENUE_PER_SCREEN times.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from itertools import groupby
from datetime import date, timedelta
from typing import Any, Callable, Iterable

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.daily_recommendation import DailyRecommendationRow
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.models.stats import PaperStatDailyRow, StatsSnapshotRunRow
from app.schemas.discovery import DiscoveryPaper
from app.services.discovery import DiscoverySnapshot, edition_id, load_discovery_snapshot

EDITION_SIZE = 300
CURATED_PER_EDITION = 60
POPULAR_PER_EDITION = 60
POPULAR_COOLDOWN_DAYS = 7
HISTORY_DAYS = 120
MAX_VENUE_SHARE = 0.25
SCREEN_SIZE = 12
VENUE_PER_SCREEN = 4
# The first screen leans on hand-picked papers; later screens follow the
# section shares.
FIRST_SCREEN = {'curated': 6, 'popular': 2, 'explore': 4}


class EditionError(RuntimeError):
    """No edition could be built; the feed keeps serving its fallback."""


@dataclass
class EditionResult:
    edition_date: date
    edition_id: str
    papers: list[DiscoveryPaper]
    sections: Counter = field(default_factory=Counter)
    pool_size: int = 0
    pool_year: int | None = None
    history_days: int = 0
    repeats: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            'date': self.edition_date.isoformat(), 'edition_id': self.edition_id,
            'size': len(self.papers), 'sections': dict(self.sections),
            'venues': dict(Counter(paper.venue for paper in self.papers).most_common()),
            'pool_year': self.pool_year, 'pool_size': self.pool_size,
            'history_days': self.history_days, 'repeats_within_history': self.repeats,
        }


def _shuffle_key(edition_date: date, paper_id: str) -> bytes:
    return hashlib.sha256(f'{edition_date.isoformat()}:{paper_id}'.encode('utf-8')).digest()


def _interleave(sections: dict[str, list[DiscoveryPaper]], size: int) -> list[tuple[str, DiscoveryPaper]]:
    """First screen by FIRST_SCREEN, then always the section furthest behind its share."""
    queues = {name: list(papers) for name, papers in sections.items()}
    total = sum(len(papers) for papers in queues.values())
    shares = {name: len(papers) / total for name, papers in queues.items()} if total else {}
    ordered: list[tuple[str, DiscoveryPaper]] = []
    taken: Counter = Counter()

    def take(name: str) -> None:
        ordered.append((name, queues[name].pop(0)))
        taken[name] += 1

    for name, count in FIRST_SCREEN.items():
        for _ in range(min(count, len(queues.get(name, [])))):
            take(name)
    while len(ordered) < min(size, total):
        position = len(ordered) + 1
        name = max(
            (name for name, queue in queues.items() if queue),
            key=lambda name: (shares[name] * position - taken[name], name),
        )
        take(name)
    return ordered


def _spread_venues(items: list[tuple[str, DiscoveryPaper]]) -> list[tuple[str, DiscoveryPaper]]:
    """Swap forward so no screen of SCREEN_SIZE cards shows one venue more than VENUE_PER_SCREEN times."""
    items = list(items)
    for index in range(len(items)):
        screen_start = index - index % SCREEN_SIZE
        counts = Counter(paper.venue for _, paper in items[screen_start:index])
        if counts[items[index][1].venue] < VENUE_PER_SCREEN:
            continue
        for later in range(index + 1, len(items)):
            if counts[items[later][1].venue] < VENUE_PER_SCREEN:
                items[index], items[later] = items[later], items[index]
                break
    return items


class DailyEditionBuilder:
    def __init__(self, curated_loader: Callable[[], DiscoverySnapshot] = load_discovery_snapshot):
        self.curated_loader = curated_loader

    async def _inputs(self, edition_date: date, year: int | None):
        async with session_scope() as session:
            pool_year = year or await session.scalar(select(func.max(DiscoveryPoolPaperRow.year)))
            pool = [] if pool_year is None else list(await session.scalars(select(DiscoveryPoolPaperRow).where(
                DiscoveryPoolPaperRow.year == pool_year,
            )))
            history = list(await session.execute(select(
                DailyRecommendationRow.recommendation_date,
                func.jsonb_path_query_array(
                    DailyRecommendationRow.payload, literal_column("'$[*].id'::jsonpath"), type_=JSONB,
                ),
            ).where(
                DailyRecommendationRow.recommendation_date >= edition_date - timedelta(days=HISTORY_DAYS),
                DailyRecommendationRow.recommendation_date < edition_date,
            )))
            latest = await session.scalar(select(func.max(StatsSnapshotRunRow.snapshot_date)).where(
                StatsSnapshotRunRow.status == 'completed',
            ))
            stats = [] if latest is None else list(await session.execute(select(
                PaperStatDailyRow.paper_id, PaperStatDailyRow.collector_count + PaperStatDailyRow.like_count,
            ).where(PaperStatDailyRow.snapshot_date == latest)))
        last_shown: dict[str, date] = {}
        for shown_on, ids in history:
            for paper_id in ids if isinstance(ids, list) else []:
                if isinstance(paper_id, str) and shown_on > last_shown.get(paper_id, date.min):
                    last_shown[paper_id] = shown_on
        popularity = {paper_id: int(count) for paper_id, count in stats if count and count > 0}
        return pool_year, pool, last_shown, popularity, len(history)

    async def build(self, edition_date: date, *, size: int = EDITION_SIZE, year: int | None = None) -> EditionResult:
        """Draw from the given pool year, by default the newest one synced."""
        pool_year, pool, last_shown, popularity, history_days = await self._inputs(edition_date, year)
        if not pool:
            raise EditionError('The discovery pool is empty; run `sync` first')
        curated = {item.paper.id: item.paper for item in self.curated_loader().items}
        papers: dict[str, DiscoveryPaper] = {row.paper_id: DiscoveryPaper(
            id=row.paper_id, title=row.title, abstract=row.abstract, authors=row.authors,
            year=row.year, venue=row.venue, image_id=row.image_id,
        ) for row in pool}
        # A curated paper always shows its optimized static thumbnail.
        papers.update(curated)

        def rotation(paper: DiscoveryPaper) -> tuple[date, bytes]:
            return last_shown.get(paper.id, date.min), _shuffle_key(edition_date, paper.id)

        chosen: dict[str, list[DiscoveryPaper]] = {'curated': [], 'popular': [], 'explore': []}
        chosen_ids: set[str] = set()
        venues: Counter = Counter()
        venue_cap = max(1, int(size * MAX_VENUE_SHARE))

        def take(section: str, candidates: Iterable[DiscoveryPaper], limit: int, *, capped: bool = True) -> None:
            for paper in candidates:
                if len(chosen[section]) >= limit or len(chosen_ids) >= size:
                    return
                if paper.id in chosen_ids or (capped and venues[paper.venue] >= venue_cap):
                    continue
                chosen[section].append(paper)
                chosen_ids.add(paper.id)
                venues[paper.venue] += 1

        take('curated', sorted(curated.values(), key=rotation), CURATED_PER_EDITION)
        cooldown = edition_date - timedelta(days=POPULAR_COOLDOWN_DAYS)
        take('popular', sorted(
            (papers[paper_id] for paper_id in popularity
             if paper_id in papers and last_shown.get(paper_id, date.min) < cooldown),
            key=lambda paper: (-popularity[paper.id], *rotation(paper)),
        ), POPULAR_PER_EDITION)
        explore = sorted((paper for paper_id, paper in papers.items() if paper_id not in curated), key=rotation)
        # Freshness outranks venue balance: the cap only chooses among papers
        # last shown on the same day, and a one-venue tier still fills the edition.
        for _, tier in groupby(explore, key=lambda paper: last_shown.get(paper.id, date.min)):
            tier = list(tier)
            take('explore', tier, size)
            take('explore', tier, size, capped=False)

        ordered = _spread_venues(_interleave(chosen, size))
        result = EditionResult(
            edition_date=edition_date, edition_id=edition_id(edition_date, [paper for _, paper in ordered]),
            papers=[paper for _, paper in ordered], sections=Counter(name for name, _ in ordered),
            pool_size=len(pool), pool_year=pool_year, history_days=history_days,
        )
        result.repeats = sum(paper.id in last_shown for paper in result.papers)
        return result

    async def publish(self, edition_date: date, *, size: int = EDITION_SIZE, year: int | None = None) -> EditionResult:
        result = await self.build(edition_date, size=size, year=year)
        payload = [paper.model_dump(mode='json') for paper in result.papers]
        async with session_scope() as session:
            statement = insert(DailyRecommendationRow).values(
                recommendation_date=edition_date, payload=payload, created_at=utc_now(),
            )
            await session.execute(statement.on_conflict_do_update(
                index_elements=[DailyRecommendationRow.recommendation_date],
                set_={'payload': statement.excluded.payload, 'created_at': statement.excluded.created_at},
            ))
        return result
