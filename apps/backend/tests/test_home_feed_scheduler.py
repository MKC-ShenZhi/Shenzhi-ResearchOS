"""The in-process scheduler for the home pool sync and the daily edition."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.discovery_pool import scheduler as scheduler_module
from app.services.discovery_pool.scheduler import HomeFeedScheduler, scheduler_enabled
from app.services.home_feed.config import pool_year


class SchedulerConfigTests(unittest.TestCase):
    def test_scheduler_is_opt_in_and_the_pool_year_is_overridable(self):
        with patch.dict(os.environ, {'HOME_FEED_SCHEDULER_ENABLED': ''}):
            self.assertFalse(scheduler_enabled())
        with patch.dict(os.environ, {'HOME_FEED_SCHEDULER_ENABLED': 'true'}):
            self.assertTrue(scheduler_enabled())
        with patch.dict(os.environ, {'HOME_FEED_POOL_YEAR': ''}):
            self.assertEqual(pool_year(), 2026)
        with patch.dict(os.environ, {'HOME_FEED_POOL_YEAR': '2027'}):
            self.assertEqual(pool_year(), 2027)


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    # An empty pool year and a day without an edition, far from real data.
    YEAR = '1903'
    NOW = datetime(2001, 3, 1, 4, 0, tzinfo=timezone.utc)  # 12:00 in Shanghai

    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        self.env = patch.dict(os.environ, {'HOME_FEED_POOL_YEAR': self.YEAR})
        self.env.start()

    async def asyncTearDown(self):
        from app.core.database import dispose_engine
        self.env.stop()
        await dispose_engine()

    def scheduler(self, sync=None):
        summary = SimpleNamespace(summary=lambda: {})
        return HomeFeedScheduler(
            sync=SimpleNamespace(sync=sync or AsyncMock(return_value=summary)),
            builder=SimpleNamespace(publish=AsyncMock(return_value=summary)),
        )

    async def test_due_jobs_run_in_order_for_the_pool_year_and_shanghai_day(self):
        scheduler = self.scheduler()
        self.assertEqual(await scheduler.run_due(self.NOW), ['sync', 'publish'])
        scheduler.sync.sync.assert_awaited_once_with(1903)
        self.assertEqual(scheduler.builder.publish.await_args.args[0].isoformat(), '2001-03-01')

    async def test_publish_waits_until_just_after_shanghai_midnight(self):
        scheduler = self.scheduler()
        just_after_midnight = datetime(2001, 2, 28, 16, 1, tzinfo=timezone.utc)  # 00:01 on 03-01
        self.assertEqual(await scheduler.run_due(just_after_midnight), ['sync'])

    async def test_a_failed_sync_is_not_retried_for_an_hour(self):
        failing = AsyncMock(side_effect=RuntimeError('knowledge base down'))
        scheduler = self.scheduler(sync=failing)
        with self.assertLogs(scheduler_module.logger, 'ERROR'):
            self.assertEqual(await scheduler.run_due(self.NOW), ['publish'])
        await scheduler.run_due(self.NOW + timedelta(minutes=30))
        self.assertEqual(failing.await_count, 1)
        with self.assertLogs(scheduler_module.logger, 'ERROR'):
            await scheduler.run_due(self.NOW + timedelta(hours=1))
        self.assertEqual(failing.await_count, 2)

    async def test_only_the_lock_holder_runs_jobs(self):
        from sqlalchemy import func, select
        from app.core.database import session_scope
        scheduler = self.scheduler()
        async with session_scope() as session:
            self.assertTrue(await session.scalar(select(func.pg_try_advisory_xact_lock(scheduler_module.LOCK_KEY))))
            self.assertEqual(await scheduler.run_due(self.NOW), [])
        scheduler.sync.sync.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
