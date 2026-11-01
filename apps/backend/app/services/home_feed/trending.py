"""Trending source: pool papers ranked by platform likes plus collections.

Reads the latest completed stats snapshot from before the list date. Today's
snapshot can still be (re)built during the day, which would change the list
under readers mid-scroll; the previous day's is final, so a given day always
yields the same list. Without platform activity it is empty
and the composer hands its slots to the other sources.
"""

from __future__ import annotations

import logging
import time
from datetime import date

from sqlalchemy import func, select

from app.core.database import session_scope
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.models.stats import PaperStatDailyRow, StatsSnapshotRunRow
from app.schemas.discovery import DiscoveryPaper
from app.services.home_feed import config
from app.services.home_feed.rules import admit

logger = logging.getLogger(__name__)

_cache: dict[date, tuple[float, list[DiscoveryPaper]]] = {}


async def load_trending(ordering_date: date) -> list[DiscoveryPaper]:
    cached = _cache.get(ordering_date)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        async with session_scope() as session:
            snapshot_date = await session.scalar(select(func.max(StatsSnapshotRunRow.snapshot_date)).where(
                StatsSnapshotRunRow.status == 'completed', StatsSnapshotRunRow.snapshot_date < ordering_date,
            ))
            pool_year = await session.scalar(select(func.max(DiscoveryPoolPaperRow.year)))
            rows = [] if snapshot_date is None or pool_year is None else list(await session.execute(
                select(DiscoveryPoolPaperRow)
                .join(PaperStatDailyRow, PaperStatDailyRow.paper_id == DiscoveryPoolPaperRow.paper_id)
                .where(
                    PaperStatDailyRow.snapshot_date == snapshot_date,
                    DiscoveryPoolPaperRow.year == pool_year,
                    PaperStatDailyRow.like_count + PaperStatDailyRow.collector_count > 0,
                )
                .order_by(
                    (PaperStatDailyRow.like_count + PaperStatDailyRow.collector_count).desc(),
                    DiscoveryPoolPaperRow.paper_id,
                )
                .limit(config.TRENDING_LIMIT),
            ))
        papers = [paper for (row,) in rows if (paper := admit(row.paper_fields())[0]) is not None]
    except Exception as error:  # noqa: BLE001 - a missing source only frees its slots
        logger.warning('Trending home papers unavailable (%s)', type(error).__name__)
        papers = []
    _cache[ordering_date] = (time.monotonic() + config.SOURCE_CACHE_SECONDS, papers)
    return papers
