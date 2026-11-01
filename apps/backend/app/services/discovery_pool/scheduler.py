"""In-process scheduling for the home feed's periodic jobs.

Opt-in with ``HOME_FEED_SCHEDULER_ENABLED=true``. Every CHECK_INTERVAL the
process tries a Postgres advisory lock; only the holder runs what is due, so
several workers or instances never duplicate a job:

- ``sync`` when the pool year has no papers or was synced SYNC_INTERVAL ago;
- ``publish`` when today's edition (Shanghai) is missing and it is past PUBLISH_AFTER;
- ``purge`` every PURGE_INTERVAL: expired recommendation snapshots, behavior
  events past retention, and daily editions no longer read as history.

Sync and publish due-ness is read from the database, so a restart or a missed
tick simply catches up on the next one. A failed sync is not retried for
SYNC_RETRY_DELAY. Purging is idempotent; after a restart it just runs again.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, time, timedelta

from sqlalchemy import exists, func, select

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.daily_recommendation import DailyRecommendationRow
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.services.discovery import SHANGHAI_TIMEZONE
from app.services.discovery_pool.edition import DailyEditionBuilder
from app.services.discovery_pool.sync import DiscoveryPoolSync
from app.services.home_feed.config import pool_year
from app.services.recommendation.maintenance import purge_expired

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 600
SYNC_INTERVAL = timedelta(days=7)
SYNC_RETRY_DELAY = timedelta(hours=1)
PUBLISH_AFTER = time(0, 5)
# Recommendation snapshots live an hour; purging hourly keeps the table near one hour of first pages.
PURGE_INTERVAL = timedelta(hours=1)
# Arbitrary constant shared by every instance of this deployment.
LOCK_KEY = 7_402_118_031


def scheduler_enabled() -> bool:
    return os.getenv('HOME_FEED_SCHEDULER_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}


class HomeFeedScheduler:
    def __init__(self, sync: DiscoveryPoolSync | None = None, builder: DailyEditionBuilder | None = None):
        self.sync = sync or DiscoveryPoolSync()
        self.builder = builder or DailyEditionBuilder()
        self._sync_failed_at: datetime | None = None
        self._purged_at: datetime | None = None

    async def run_due(self, now: datetime | None = None) -> list[str]:
        """Run every job that is due now; returns the jobs that ran."""
        now = now or utc_now()
        local = now.astimezone(SHANGHAI_TIMEZONE)
        year = pool_year()
        ran: list[str] = []
        async with session_scope() as session:
            if not await session.scalar(select(func.pg_try_advisory_xact_lock(LOCK_KEY))):
                return ran
            last_sync = await session.scalar(
                select(func.max(DiscoveryPoolPaperRow.synced_at)).where(DiscoveryPoolPaperRow.year == year),
            )
            retry_blocked = self._sync_failed_at is not None and now - self._sync_failed_at < SYNC_RETRY_DELAY
            if (last_sync is None or now - last_sync >= SYNC_INTERVAL) and not retry_blocked:
                try:
                    result = await self.sync.sync(year)
                    self._sync_failed_at = None
                    ran.append('sync')
                    logger.info('Home pool synced: %s', result.summary())
                except Exception:  # noqa: BLE001 - the existing pool keeps serving
                    self._sync_failed_at = now
                    logger.exception('Home pool sync failed; the existing pool is kept')
            published = await session.scalar(select(exists().where(
                DailyRecommendationRow.recommendation_date == local.date(),
            )))
            if not published and local.time() >= PUBLISH_AFTER:
                try:
                    result = await self.builder.publish(local.date(), year=year)
                    ran.append('publish')
                    logger.info('Home daily edition published: %s', result.summary())
                except Exception:  # noqa: BLE001 - the feed falls back to an older edition
                    logger.exception('Home daily edition publish failed')
            if self._purged_at is None or now - self._purged_at >= PURGE_INTERVAL:
                try:
                    events, snapshots = await purge_expired(now)
                    editions = await self.builder.purge(local.date())
                    self._purged_at = now
                    ran.append('purge')
                    logger.info('Home feed purge: events=%d snapshots=%d editions=%d', events, snapshots, editions)
                except Exception:  # noqa: BLE001 - retried on the next tick
                    logger.exception('Home feed purge failed')
        return ran

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_due()
            except Exception:  # noqa: BLE001 - one bad tick must not stop scheduling
                logger.exception('Home feed scheduler tick failed')
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start_home_feed_scheduler() -> asyncio.Task | None:
    if not scheduler_enabled():
        return None
    logger.info('Home feed scheduler started')
    return asyncio.create_task(HomeFeedScheduler().run_forever(), name='home-feed-scheduler')


async def stop_home_feed_scheduler(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
