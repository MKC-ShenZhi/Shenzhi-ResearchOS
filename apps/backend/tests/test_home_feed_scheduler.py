"""The in-process scheduler for the home pool sync, the daily edition and retention purges."""

import asyncio
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.discovery_pool import scheduler as scheduler_module
from app.services.discovery_pool.scheduler import HomeFeedScheduler, scheduler_enabled
from app.services.home_feed.config import pool_year


class SchedulerConfigTests(unittest.TestCase):
    def test_scheduler_is_opt_in_and_the_pool_year_is_overridable(self):
        with patch.dict(os.environ, {'BACKGROUND_JOBS_ENABLED': ''}):
            os.environ.pop('BACKGROUND_JOBS_ENABLED')
            self.assertFalse(scheduler_enabled())
            self.assertIsNone(scheduler_module.start_home_feed_scheduler())
        with patch.dict(os.environ, {'BACKGROUND_JOBS_ENABLED': 'true'}):
            self.assertTrue(scheduler_enabled())
        with patch.dict(os.environ, {'HOME_FEED_POOL_YEAR': ''}):
            self.assertEqual(pool_year(), 2026)
        with patch.dict(os.environ, {'HOME_FEED_POOL_YEAR': '2027'}):
            self.assertEqual(pool_year(), 2027)


class SchedulerStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_starts_the_scheduler_and_false_skips_work(self):
        started = asyncio.Event()
        with patch.dict(os.environ, {'BACKGROUND_JOBS_ENABLED': 'true'}), patch.object(
            HomeFeedScheduler, 'run_due', AsyncMock(side_effect=started.set),
        ):
            task = scheduler_module.start_home_feed_scheduler()
            try:
                await asyncio.wait_for(started.wait(), timeout=2)
            finally:
                await scheduler_module.stop_home_feed_scheduler(task)

        with patch.dict(os.environ, {'BACKGROUND_JOBS_ENABLED': 'false'}), patch.object(
            scheduler_module.ConferenceSync, 'run', AsyncMock(),
        ) as sync_deadlines:
            self.assertIsNone(scheduler_module.start_home_feed_scheduler())
            self.assertEqual(await HomeFeedScheduler().run_due(), [])
            sync_deadlines.assert_not_awaited()


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    # An empty pool year and a day without an edition, far from real data.
    YEAR = '1903'
    NOW = datetime(2001, 3, 1, 4, 0, tzinfo=timezone.utc)  # 12:00 in Shanghai

    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        self.enterContext(patch.dict(os.environ, {'HOME_FEED_POOL_YEAR': self.YEAR, 'BACKGROUND_JOBS_ENABLED': 'true'}))
        self.sync_deadlines = self.enterContext(patch.object(
            scheduler_module.ConferenceSync, 'run', AsyncMock(return_value={'status': 'not-due'}),
        ))

    async def asyncTearDown(self):
        from app.core.database import dispose_engine
        await dispose_engine()

    def scheduler(self, sync=None):
        summary = SimpleNamespace(summary=lambda: {})
        return HomeFeedScheduler(
            sync=SimpleNamespace(sync=sync or AsyncMock(return_value=summary)),
            builder=SimpleNamespace(publish=AsyncMock(return_value=summary), purge=AsyncMock(return_value=0)),
        )

    async def test_due_jobs_run_in_order_for_the_pool_year_and_shanghai_day(self):
        self.sync_deadlines.return_value = {'status': 'updated'}
        scheduler = self.scheduler()
        self.assertEqual(await scheduler.run_due(self.NOW), ['conferences', 'sync', 'publish', 'purge'])
        self.sync_deadlines.assert_awaited_once_with(now=self.NOW)
        scheduler.sync.sync.assert_awaited_once_with(1903)
        self.assertEqual(scheduler.builder.publish.await_args.args[0].isoformat(), '2001-03-01')

    async def test_failed_deadline_sync_does_not_block_home_jobs(self):
        self.sync_deadlines.side_effect = RuntimeError('GitHub down')
        with self.assertLogs(scheduler_module.logger, 'ERROR'):
            self.assertEqual(await self.scheduler().run_due(self.NOW), ['sync', 'publish', 'purge'])

    async def test_publish_waits_until_just_after_shanghai_midnight(self):
        scheduler = self.scheduler()
        just_after_midnight = datetime(2001, 2, 28, 16, 1, tzinfo=timezone.utc)  # 00:01 on 03-01
        self.assertEqual(await scheduler.run_due(just_after_midnight), ['sync', 'purge'])

    async def test_a_failed_sync_is_not_retried_for_an_hour(self):
        failing = AsyncMock(side_effect=RuntimeError('knowledge base down'))
        scheduler = self.scheduler(sync=failing)
        with self.assertLogs(scheduler_module.logger, 'ERROR'):
            self.assertEqual(await scheduler.run_due(self.NOW), ['publish', 'purge'])
        await scheduler.run_due(self.NOW + timedelta(minutes=30))
        self.assertEqual(failing.await_count, 1)
        with self.assertLogs(scheduler_module.logger, 'ERROR'):
            await scheduler.run_due(self.NOW + timedelta(hours=1))
        self.assertEqual(failing.await_count, 2)

    async def test_purge_runs_hourly_and_retries_after_a_failure(self):
        scheduler = self.scheduler()
        with patch.object(scheduler_module, 'purge_expired', AsyncMock(return_value=(0, 0))) as purge:
            await scheduler.run_due(self.NOW)
            self.assertNotIn('purge', await scheduler.run_due(self.NOW + timedelta(minutes=50)))
            self.assertIn('purge', await scheduler.run_due(self.NOW + timedelta(hours=1)))
        self.assertEqual(purge.await_count, 2)
        scheduler.builder.purge.assert_awaited_with(date(2001, 3, 1))

        failing = self.scheduler()
        with patch.object(scheduler_module, 'purge_expired', AsyncMock(side_effect=RuntimeError('db'))):
            with self.assertLogs(scheduler_module.logger, 'ERROR'):
                self.assertNotIn('purge', await failing.run_due(self.NOW))
        self.assertIn('purge', await failing.run_due(self.NOW + timedelta(minutes=10)))

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
