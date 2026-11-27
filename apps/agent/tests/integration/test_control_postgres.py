"""Real row locks and uniqueness, only on the existing isolated acceptance DB.

Set AGENT_TEST_DATABASE_URL explicitly. Tests never migrate or recreate tables,
refuse a busy queue, and delete only rows belonging to their random test owner.
"""
from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_contracts import ExecutionReport, RunStatus, TaskSubmission
from agent_contracts.v2 import TaskSubmissionV2
from agent_contracts.wire import TaskSubmissionWire
from agent_contracts.canonical import request_digest_v1
from agent_app.control import repository
from agent_app.errors import BusinessError
from agent_app.infrastructure.models import RunRow, TaskRow


@unittest.skipUnless(os.getenv('AGENT_TEST_DATABASE_URL'), 'isolated Agent PostgreSQL not selected')
class ControlPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = os.environ['AGENT_TEST_DATABASE_URL']
        parsed = urlsplit(url)
        if (parsed.hostname not in ('localhost', '127.0.0.1') or parsed.port != 55432
                or parsed.path != '/shenzhi_m0c1_agent'):
            raise RuntimeError('Only the existing local M0-C1 Agent database is allowed')
        self.engine = create_async_engine(url)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.owner = 'integration-review:' + uuid.uuid4().hex
        async with self.factory() as db:
            busy = await db.scalar(select(func.count()).select_from(TaskRow).where(
                TaskRow.status.in_(('queued', 'running', 'cancelling'))))
        if busy:
            await self.engine.dispose()
            self.skipTest('Existing acceptance queue is busy; no tasks will be claimed')

    async def asyncTearDown(self):
        async with self.factory() as db:
            await db.execute(delete(TaskRow).where(TaskRow.owner_id == self.owner))
            await db.commit()
        await self.engine.dispose()

    async def submit(self, **kwargs):
        submission = TaskSubmission(owner_id=self.owner, **kwargs)
        request = self.wire(submission)
        envelope = self.envelope(request)
        async with self.factory() as db:
            task = await repository.submit(db, submission, metering=envelope)
            await self.bind_profile(db, task.task_id)
            return task

    @staticmethod
    def wire(submission):
        return TaskSubmissionWire(owner_id=submission.owner_id, prompt=submission.prompt,
            session_id=submission.session_id, turn_id=submission.turn_id,
            input_ref=submission.input_ref, idempotency_key=submission.idempotency_key,
            mode=submission.mode, model=submission.model, workspace_id=submission.workspace_id,
            skills=list(submission.skills), budget={
                'max_duration_s': submission.budget.max_duration_s,
                'max_tool_calls': submission.budget.max_tool_calls,
                'max_model_tokens': submission.budget.max_model_tokens,
            }, history=list(submission.history))

    def envelope(self, request):
        return TaskSubmissionV2(schema_version=1, request=request, owner_id=self.owner,
            metering_profile_id='profile:'+uuid.uuid4().hex, metering_context='observation_only',
            submission_id=None, request_digest=request_digest_v1(request.model_dump(mode='json')),
            agent_audience='agent-test', budget_grant=None, permission_snapshot=None, call_bounds={})

    async def bind_profile(self, db, task_id):
        from agent_app.infrastructure.metering_models import TaskMeteringRow
        profile = await db.get(TaskMeteringRow, task_id)
        profile.binding = {'schema_version': 1, 'task_id': task_id,
                           'metering_profile_id': profile.profile_id, 'owner_id': self.owner,
                           'metering_context': 'observation_only'}
        profile.binding_status = 'bound'
        await db.commit()

    async def race_submissions(self, prompts):
        ready = asyncio.Event()
        count = 0

        class RacingSession(AsyncSession):
            checked = False

            async def scalar(inner, statement, *args, **kwargs):
                nonlocal count
                result = await super(RacingSession, inner).scalar(statement, *args, **kwargs)
                if not inner.checked:
                    inner.checked = True
                    count += 1
                    if count == len(prompts):
                        ready.set()
                    await ready.wait()
                return result

        factory = async_sessionmaker(self.engine, class_=RacingSession, expire_on_commit=False)

        async def send(prompt):
            submission = TaskSubmission(owner_id=self.owner, prompt=prompt, idempotency_key='concurrent-key')
            request = self.wire(submission)
            envelope = self.envelope(request)
            async with factory() as db:
                task = await repository.submit(db, submission, metering=envelope)
                await self.bind_profile(db, task.task_id)
                return task

        return await asyncio.wait_for(asyncio.gather(
            *(send(prompt) for prompt in prompts), return_exceptions=True), timeout=10)

    async def test_concurrent_same_key_reuses_one_task_and_run(self):
        results = await self.race_submissions(['same', 'same'])
        self.assertFalse(any(isinstance(item, BaseException) for item in results), results)
        self.assertEqual(results[0].task_id, results[1].task_id)
        async with self.factory() as db:
            runs = await repository.list_task_runs(db, results[0].task_id, self.owner)
        self.assertEqual(len(runs), 1)

    async def test_concurrent_conflicting_key_returns_business_conflict(self):
        results = await self.race_submissions(['first', 'different'])
        errors = [item for item in results if isinstance(item, BaseException)]
        self.assertEqual(len(errors), 1, results)
        self.assertIsInstance(errors[0], BusinessError)
        self.assertEqual(errors[0].status, 409)

    async def test_cancel_and_report_lock_order_and_no_retry_after_cancel(self):
        task = await self.submit(prompt='cancel/report race')
        async with self.factory() as db:
            request, token, _ = await repository.claim_run(db, 'review-worker')
        self.assertEqual(request.task_id, task.task_id)
        report_started = asyncio.Event()

        async def report():
            async with self.factory() as db:
                report_started.set()
                await repository.record_report(db, ExecutionReport(
                    run_id=request.run_id, task_id=task.task_id, status=RunStatus.FAILED,
                ), 'review-worker', token)

        async with self.factory() as cancelling:
            row = await cancelling.scalar(select(TaskRow).where(
                TaskRow.task_id == task.task_id).with_for_update())
            writer = asyncio.create_task(report())
            try:
                await report_started.wait()
                await asyncio.sleep(0.1)
                # A reporter must wait on Task without holding Run. The old
                # Run -> Task implementation blocks this lock and deadlocks.
                await asyncio.wait_for(cancelling.scalar(select(RunRow).where(
                    RunRow.run_id == request.run_id).with_for_update()), timeout=2)
                row.cancel_requested = True
                row.status = 'cancelling'
                await cancelling.commit()
                await asyncio.wait_for(writer, timeout=5)
            finally:
                writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)
        async with self.factory() as db:
            self.assertEqual(await repository.list_task_runs(db, task.task_id, self.owner),
                             [request.run_id])
            current = await repository.get_task(db, task.task_id, self.owner)
            self.assertEqual(current.status.value, 'failed')

    async def test_mock_and_real_claims_are_separate_on_postgres(self):
        real = await self.submit(prompt='real', model='provider/model')
        mock = await self.submit(prompt='mock', model='demo/m1', session_id='ses_mock', turn_id='turn_mock')
        async with self.factory() as db:
            request, _, _ = await repository.claim_run(db, 'mock-worker', demo_mode=True)
            self.assertEqual(request.task_id, mock.task_id)
            request, _, _ = await repository.claim_run(db, 'real-worker')
            self.assertEqual(request.task_id, real.task_id)
