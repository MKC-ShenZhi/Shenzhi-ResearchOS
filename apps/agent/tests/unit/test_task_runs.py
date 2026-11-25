"""Complete Task Run enumeration through real Control SQL and the read-only API."""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
from agent_contracts import ExecutionReport, RunStatus, TaskSubmission
from agent_contracts.v2 import TaskSubmissionV2
from agent_contracts.wire import TaskSubmissionWire
from agent_contracts.canonical import request_digest_v1
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from agent_app.control import repository
from agent_app.infrastructure.database import get_session
from agent_app.infrastructure.models import Base, RunRow
from agent_app.main import app
from agent_app.infrastructure.metering_models import TaskMeteringRow
from tests.unit.test_worker_takeover import MemorySession


class TaskRunHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch.dict('os.environ', {'AGENT_SERVICE_TOKEN': 'test-token'}))
        self.enterContext(patch.dict('os.environ', {'AGENT_GATEWAY_TOKEN': 'gateway-test'}))
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
            headers={'Authorization': 'Bearer gateway-test'},
        )
        self.addAsyncCleanup(self.client.aclose)
        self.task = await self.submit('owner', 'run')

    async def submit(self, owner, prompt, **kwargs):
        submission = TaskSubmission(owner_id=owner, prompt=prompt, **kwargs)
        request = TaskSubmissionWire(owner_id=owner, prompt=prompt, session_id=submission.session_id,
            turn_id=submission.turn_id, input_ref=submission.input_ref,
            idempotency_key=submission.idempotency_key, mode=submission.mode, model=submission.model,
            workspace_id=submission.workspace_id, skills=list(submission.skills),
            budget={'max_duration_s': submission.budget.max_duration_s,
                    'max_tool_calls': submission.budget.max_tool_calls,
                    'max_model_tokens': submission.budget.max_model_tokens},
            history=list(submission.history))
        metering = TaskSubmissionV2(schema_version=1, request=request, owner_id=owner,
            metering_profile_id='profile:'+uuid.uuid4().hex, metering_context='observation_only',
            submission_id=None, request_digest=request_digest_v1(request.model_dump(mode='json')),
            agent_audience='agent-test', budget_grant=None, permission_snapshot=None, call_bounds={})
        task = await repository.submit(self.db, submission, metering=metering)
        profile = await self.db.get(TaskMeteringRow, task.task_id)
        profile.binding_status = 'bound'
        await self.db.commit()
        return task

    async def mark_v2(self, task, owner='owner'):
        profile = await self.db.get(TaskMeteringRow, task.task_id)
        profile.binding_status = 'bound'
        await self.db.commit()

    async def history(self, *, owner='owner', task_id=None):
        return await self.client.get(f'/internal/v2/tasks/{task_id or self.task.task_id}/runs',
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
        self.assertEqual((await self.history()).json(), {'schema_version': 1, 'run_ids': expected})
        for status in (RunStatus.FAILED, RunStatus.TIMED_OUT):
            await self.retry(status)
            task = await repository.get_task(self.db, self.task.task_id, 'owner')
            expected.append(task.current_run_id)
            self.assertEqual((await self.history()).json(), {'schema_version': 1, 'run_ids': expected})
        await self.retry(RunStatus.COMPLETED)
        # Wall clock order is deliberately opposite to retry order.
        for row in self.sql.scalars(select(RunRow)).all():
            row.created_at = self.now - timedelta(days=row.attempt)
        self.sql.commit()
        response = await self.history()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'schema_version': 1, 'run_ids': expected})
        self.assertEqual(await repository.list_task_runs(self.db, self.task.task_id, 'owner'), expected)

    async def test_cross_owner_and_missing_task_are_hidden(self):
        await self.retry(RunStatus.FAILED)
        other = await self.submit('other', 'other')
        await self.mark_v2(other, 'other')
        denied = await self.history(owner='other')
        missing = await self.history(task_id='missing')
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.status_code, missing.status_code)
        allowed = await self.history(owner='other', task_id=other.task_id)
        self.assertEqual(allowed.json(), {'schema_version': 1, 'run_ids': [other.current_run_id]})

    async def test_cancelled_execution_failure_does_not_create_retry(self):
        request, token, _ = await repository.claim_run(self.db, 'worker')
        await repository.request_cancel(self.db, request.task_id, 'owner')
        await repository.record_report(self.db, ExecutionReport(
            run_id=request.run_id, task_id=request.task_id, status=RunStatus.FAILED,
        ), 'worker', token)
        self.assertEqual(await repository.list_task_runs(self.db, request.task_id, 'owner'),
                         [request.run_id])
        current = await repository.get_task(self.db, request.task_id, 'owner')
        self.assertNotEqual(current.status.value, 'queued')

    async def test_timeout_is_recorded_and_retried_as_a_new_v2_run(self):
        request, token, _ = await repository.claim_run(self.db, 'worker')
        await repository.record_report(self.db, ExecutionReport(
            run_id=request.run_id, task_id=request.task_id, status=RunStatus.TIMED_OUT,
        ), 'worker', token)
        current = await repository.get_task(self.db, request.task_id, 'owner')
        self.assertEqual(current.status.value, 'queued')
        self.assertNotEqual(current.current_run_id, request.run_id)
        self.assertEqual(await repository.list_task_runs(self.db, request.task_id, 'owner'),
                         [request.run_id, current.current_run_id])

    async def test_claim_filters_mock_and_real_runs_including_expired_leases(self):
        demo = await self.submit('owner', 'mock', model='demo/m1', session_id='ses_demo', turn_id='turn_demo')
        real, _, _ = await repository.claim_run(self.db, 'real')
        mock, _, _ = await repository.claim_run(self.db, 'demo', demo_mode=True)
        self.assertEqual(real.task_id, self.task.task_id)
        self.assertEqual(mock.task_id, demo.task_id)
        self.assertIsNone(await repository.claim_run(self.db, 'real'))
        self.assertIsNone(await repository.claim_run(self.db, 'demo', demo_mode=True))
        await repository.request_cancel(self.db, real.task_id, 'owner')
        self.now += timedelta(seconds=repository.WORKER_LEASE_SECONDS + 1)
        taken, _, _ = await repository.claim_run(self.db, 'demo-2', demo_mode=True)
        self.assertEqual(taken.task_id, demo.task_id)
        taken, _, _ = await repository.claim_run(self.db, 'real-2')
        self.assertEqual(taken.task_id, self.task.task_id)
        current = await repository.get_task(self.db, taken.task_id, 'owner')
        self.assertEqual(current.status.value, 'cancelling')

    async def test_v1_internal_prefix_is_retired(self):
        response = await self.client.post('/internal/v1/worker/claim', json={
            'worker_id': 'legacy-worker', 'demo_mode': False,
        })
        self.assertEqual(response.status_code, 404)

    async def test_service_credential_is_required_and_read_does_not_mutate_task(self):
        before = await repository.get_task(self.db, self.task.task_id, 'owner')
        response = await self.client.get(f'/internal/v2/tasks/{self.task.task_id}/runs',
                                         params={'owner_id': 'owner'},
                                         headers={'Authorization': 'Bearer wrong'})
        self.assertEqual(response.status_code, 403)
        for _ in range(2):
            self.assertEqual((await self.history()).json(), {'schema_version': 1, 'run_ids': [before.current_run_id]})
        after = await repository.get_task(self.db, self.task.task_id, 'owner')
        self.assertEqual((after.status, after.current_run_id), (before.status, before.current_run_id))


if __name__ == '__main__':
    unittest.main()
