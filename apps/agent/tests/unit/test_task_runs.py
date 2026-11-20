"""Complete Task Run enumeration through real Control SQL and the read-only API."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
from agent_contracts import ExecutionReport, RunStatus, TaskSubmission
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from agent_app.control import repository
from agent_app.infrastructure.database import get_session
from agent_app.infrastructure.models import Base, RunRow
from agent_app.main import app
from tests.unit.test_worker_takeover import MemorySession


class TaskRunHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch.dict('os.environ', {'AGENT_SERVICE_TOKEN': 'test-token'}))
        self.now = datetime(2026, 11, 18, 12)
        self.enterContext(patch.object(repository, '_now', side_effect=lambda: self.now))
        engine = create_engine('sqlite:///:memory:')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sql = Session(engine, expire_on_commit=False)
        self.addCleanup(self.sql.close)
        self.db = MemorySession(self.sql)

        async def dependency():
            yield self.db

        self.enterContext(patch.dict(app.dependency_overrides, {get_session: dependency}))
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://agent.test',
            headers={'Authorization': 'Bearer test-token'},
        )
        self.addAsyncCleanup(self.client.aclose)
        self.task = await repository.submit(self.db, TaskSubmission(owner_id='owner', prompt='run'))

    async def history(self, *, owner='owner', task_id=None):
        return await self.client.get(f'/internal/v1/tasks/{task_id or self.task.task_id}/runs',
                                     params={'owner_id': owner})

    async def retry(self, status):
        request, token, _ = await repository.claim_run(self.db, 'worker')
        await repository.record_report(self.db, ExecutionReport(
            run_id=request.run_id, task_id=request.task_id, status=status,
            result={'final_text': status.value},
        ), 'worker', token)
        self.now += timedelta(seconds=10)

    async def test_all_one_two_three_runs_in_attempt_order_despite_timestamps(self):
        expected = [self.task.current_run_id]
        self.assertEqual((await self.history()).json(), {'run_ids': expected})
        for status in (RunStatus.FAILED, RunStatus.TIMED_OUT):
            await self.retry(status)
            task = await repository.get_task(self.db, self.task.task_id, 'owner')
            expected.append(task.current_run_id)
            self.assertEqual((await self.history()).json(), {'run_ids': expected})
        await self.retry(RunStatus.COMPLETED)
        # Wall clock order is deliberately opposite to retry order.
        for row in self.sql.scalars(select(RunRow)).all():
            row.created_at = self.now - timedelta(days=row.attempt)
        self.sql.commit()
        response = await self.history()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'run_ids': expected})
        self.assertEqual(await repository.list_task_runs(self.db, self.task.task_id, 'owner'), expected)

    async def test_cross_owner_and_missing_task_are_hidden(self):
        await self.retry(RunStatus.FAILED)
        other = await repository.submit(self.db, TaskSubmission(owner_id='other', prompt='other'))
        denied = await self.history(owner='other')
        missing = await self.history(task_id='missing')
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.json(), missing.json())
        allowed = await self.history(owner='other', task_id=other.task_id)
        self.assertEqual(allowed.json(), {'run_ids': [other.current_run_id]})

    async def test_cancelled_execution_failure_does_not_create_retry(self):
        for status in (RunStatus.FAILED, RunStatus.TIMED_OUT):
            task = await repository.submit(self.db, TaskSubmission(owner_id='owner', prompt='cancel'))
            request, token, _ = await repository.claim_run(self.db, 'worker')
            # The fixture's original task may be first; use the actual claim.
            await repository.request_cancel(self.db, request.task_id, 'owner')
            await repository.record_report(self.db, ExecutionReport(
                run_id=request.run_id, task_id=request.task_id, status=status,
            ), 'worker', token)
            self.assertEqual(await repository.list_task_runs(self.db, request.task_id, 'owner'),
                             [request.run_id])
            current = await repository.get_task(self.db, request.task_id, 'owner')
            self.assertNotEqual(current.status.value, 'queued')

    async def test_claim_filters_mock_and_real_runs_including_expired_leases(self):
        demo = await repository.submit(self.db, TaskSubmission(
            owner_id='owner', prompt='mock', model='demo/m1', session_id='ses_demo', turn_id='turn_demo'))
        real, _, _ = await repository.claim_run(self.db, 'real')
        mock, _, _ = await repository.claim_run(self.db, 'demo', demo_mode=True)
        self.assertEqual(real.task_id, self.task.task_id)
        self.assertEqual(mock.task_id, demo.task_id)
        self.assertIsNone(await repository.claim_run(self.db, 'real'))
        self.assertIsNone(await repository.claim_run(self.db, 'demo', demo_mode=True))
        await repository.request_cancel(self.db, real.task_id, 'owner')
        self.now += timedelta(seconds=46)
        taken, _, _ = await repository.claim_run(self.db, 'demo-2', demo_mode=True)
        self.assertEqual(taken.task_id, demo.task_id)
        taken, _, _ = await repository.claim_run(self.db, 'real-2')
        self.assertEqual(taken.task_id, self.task.task_id)
        current = await repository.get_task(self.db, taken.task_id, 'owner')
        self.assertEqual(current.status.value, 'cancelling')

    async def test_api_rejects_mixed_mode_submission_and_worker(self):
        for demo_mode in ('0', '1'):
            with patch.dict('os.environ', {'AGENT_DEMO_MODE': demo_mode}):
                rejected = await self.client.post('/internal/v1/tasks', json={
                    'owner_id': 'owner', 'prompt': 'wrong mode',
                    'model': 'real/model' if demo_mode == '1' else 'demo/m1',
                    'session_id': 'ses_demo',
                    'turn_id': 'turn_demo',
                })
                self.assertEqual(rejected.status_code, 409)
                rejected = await self.client.post('/internal/v1/worker/claim', json={
                    'worker_id': 'wrong-mode', 'demo_mode': demo_mode != '1',
                })
                self.assertEqual(rejected.status_code, 409)

    async def test_service_credential_is_required_and_read_does_not_mutate_task(self):
        before = await repository.get_task(self.db, self.task.task_id, 'owner')
        response = await self.client.get(f'/internal/v1/tasks/{self.task.task_id}/runs',
                                         params={'owner_id': 'owner'},
                                         headers={'Authorization': 'Bearer wrong'})
        self.assertEqual(response.status_code, 401)
        for _ in range(2):
            self.assertEqual((await self.history()).json(), {'run_ids': [before.current_run_id]})
        after = await repository.get_task(self.db, self.task.task_id, 'owner')
        self.assertEqual((after.status, after.current_run_id), (before.status, before.current_run_id))


if __name__ == '__main__':
    unittest.main()
