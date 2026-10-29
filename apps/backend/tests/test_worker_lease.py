"""Heartbeat supervision for durable Chat and Agent work (no database required)."""
import asyncio
import unittest

from app.core.worker_lease import WorkerLeaseLost, run_with_heartbeat


class WorkerLeaseHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_renewal_error_does_not_cancel_work_before_expiry(self):
        attempts = 0

        async def renew():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError('database briefly unavailable')
            return True

        async def work():
            await asyncio.sleep(0.08)
            return 'done'

        result = await run_with_heartbeat(work, renew, interval_seconds=0.01, lease_seconds=1)

        self.assertEqual(result, 'done')
        self.assertGreater(attempts, 1)

    async def test_renewal_errors_abort_before_the_lease_can_lapse(self):
        cancelled = asyncio.Event()

        async def renew():
            raise ConnectionError('database unavailable')

        async def work():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with self.assertRaises(ConnectionError):
            await run_with_heartbeat(work, renew, interval_seconds=0.01, lease_seconds=0.05)
        self.assertTrue(cancelled.is_set())

    async def test_lost_ownership_cancels_work_immediately(self):
        async def renew():
            return False

        with self.assertRaises(WorkerLeaseLost):
            await run_with_heartbeat(asyncio.Event().wait, renew, interval_seconds=0.01)

    async def test_finished_row_stops_heartbeat_and_lets_work_complete(self):
        async def renew():
            return None

        async def work():
            await asyncio.sleep(0.05)
            return 'persisted'

        self.assertEqual(
            await run_with_heartbeat(work, renew, interval_seconds=0.01), 'persisted',
        )


if __name__ == '__main__':
    unittest.main()
