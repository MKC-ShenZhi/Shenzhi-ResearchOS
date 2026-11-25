"""Exercise real Control SQL and Worker/API wiring against SQLite in memory.

No PostgreSQL locking/concurrency claim is made: this fixture evaluates the
repository's predicates, persistence and fencing, with an explicit lease clock.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
from agent_contracts import TaskSubmission
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from agent_app.control import repository
from agent_app.execution.runtime import AgentRuntime
from agent_app.execution.types import StopReason
from agent_app.infrastructure.database import get_session
from agent_app.infrastructure.models import Base, RunEventRow, RunRow, TaskRow
from agent_app.integrations.llm.agent_stream import Finish, TextDelta
from agent_app.main import app
from agent_app.worker import host
from tests.unit.test_agent import FakeProvider


class MemorySession:
    """Async facade over the existing SQLAlchemy dependency, without a new driver."""

    def __init__(self, session):
        self.session = session

    def add(self, row):
        self.session.add(row)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def scalars(self, statement):
        return self.session.scalars(statement)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()


class WorkerTakeoverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch.dict('os.environ', {
            'AGENT_SERVICE_TOKEN': 'test-token', 'AGENT_WORKER_PROTOCOL': '1',
        }))
        # SQLite returns naive datetimes; keep the controlled clock consistent.
        self.now = datetime(2026, 11, 18, 12)
        self.enterContext(patch.object(repository, '_now', side_effect=lambda: self.now))
        engine = create_engine('sqlite:///:memory:')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.session = Session(engine, expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.db = MemorySession(self.session)

        async def session_dependency():
            yield self.db

        self.enterContext(patch.dict(app.dependency_overrides, {get_session: session_dependency}))
        self.control = host.AgentControlClient(transport=httpx.ASGITransport(app=app))
        self.addAsyncCleanup(self.control.close)
        self.task = await repository.submit(self.db, TaskSubmission(owner_id='owner', prompt='run'))

    def expire_lease(self):
        self.now += timedelta(seconds=repository.WORKER_LEASE_SECONDS + 1)

    async def emit(self, claim, worker, seq, *, text='partial'):
        run = claim['run']
        return await self.control.post(f"/internal/v1/runs/{run['run_id']}/events", {
            'task_id': run['task_id'], 'run_id': run['run_id'], 'seq': seq,
            'turn': 1, 'name': 'delta', 'data': {'text': text},
            'occurred_at': self.now.isoformat(),
            'worker_id': worker, 'lease_token': claim['lease_token'],
        })

    async def report(self, claim, worker, *, status='completed', text='complete'):
        run = claim['run']
        return await self.control.post(f"/internal/v1/runs/{run['run_id']}/report", {
            'task_id': run['task_id'], 'run_id': run['run_id'], 'status': status,
            'result': {'final_text': text}, 'usage': {},
            'worker_id': worker, 'lease_token': claim['lease_token'],
        })

    async def rejected(self, operation):
        with self.assertRaises(httpx.HTTPStatusError) as error:
            await operation
        self.assertEqual(error.exception.response.status_code, 409)

    def events(self, run_id):
        return self.session.scalars(select(RunEventRow).where(
            RunEventRow.run_id == run_id,
        ).order_by(RunEventRow.seq)).all()

    async def execute(self, claim, worker):
        runtime = AgentRuntime(provider=FakeProvider([
            [TextDelta('complete'), Finish(StopReason.STOP)],
        ]))
        with patch.object(host, 'build_runtime', return_value=runtime):
            await host.execute_claim(self.control, claim, worker)

    async def test_normal_worker_starts_at_one_and_completes(self):
        claim = await self.control.claim('worker-a')
        self.assertEqual((claim['lease_token'], claim['event_seq']), (1, 0))
        await self.execute(claim, 'worker-a')
        rows = self.events(claim['run']['run_id'])
        self.assertEqual([row.seq for row in rows], list(range(1, len(rows) + 1)))
        run = self.session.get(RunRow, claim['run']['run_id'])
        self.assertEqual(run.report_json['status'], 'completed')
        self.assertEqual(run.report_json['result']['final_text'], 'complete')

    async def test_takeover_worker_continues_sequence_and_completes(self):
        first = await self.control.claim('worker-a')
        await self.emit(first, 'worker-a', 1)
        self.expire_lease()
        second = await self.control.claim('worker-b')
        self.assertEqual(second['run']['run_id'], first['run']['run_id'])
        self.assertEqual((second['lease_token'], second['event_seq']), (2, 1))
        await self.execute(second, 'worker-b')
        rows = self.events(first['run']['run_id'])
        self.assertEqual([row.seq for row in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(rows[0].data, {'text': 'partial'})
        self.assertEqual(rows[1].name, 'run_start')
        self.assertEqual(self.session.get(RunRow, first['run']['run_id']).status, 'completed')

    async def test_stale_token_cannot_publish_renew_or_finish_new_lease(self):
        first = await self.control.claim('worker-a')
        await self.emit(first, 'worker-a', 1)
        self.expire_lease()
        second = await self.control.claim('worker-b')
        await self.rejected(self.emit(first, 'worker-a', 2, text='stale'))
        await self.rejected(self.report(first, 'worker-a', status='failed', text='stale'))
        stale = await self.control.heartbeat(first['run']['run_id'], 'worker-a', 1)
        self.assertFalse(stale.active)
        current = await self.control.heartbeat(second['run']['run_id'], 'worker-b', 2)
        self.assertTrue(current.active)
        run = self.session.get(RunRow, second['run']['run_id'])
        self.assertEqual((run.worker_id, run.lease_token, run.status), ('worker-b', 2, 'running'))
        self.assertIsNone(run.report_json)
        self.assertEqual([row.seq for row in self.events(run.run_id)], [1])
        await self.emit(second, 'worker-b', 2)
        await self.report(second, 'worker-b')

    async def test_takeover_uses_max_sequence_instead_of_event_count(self):
        first = await self.control.claim('worker-a')
        await self.emit(first, 'worker-a', 3)
        self.expire_lease()
        second = await self.control.claim('worker-b')
        self.assertEqual(second['event_seq'], 3)
        await self.execute(second, 'worker-b')
        rows = self.events(first['run']['run_id'])
        self.assertEqual(rows[1].seq, 4)
        self.assertEqual([row.seq for row in rows], list(range(3, 3 + len(rows))))

    async def test_repeated_takeovers_and_heartbeats_do_not_regress_or_duplicate(self):
        previous = []
        for index, worker in enumerate(('worker-a', 'worker-b', 'worker-c'), 1):
            claim = await self.control.claim(worker)
            self.assertEqual((claim['lease_token'], claim['event_seq']), (index, index - 1))
            run_id = claim['run']['run_id']
            for _ in range(2):
                self.assertTrue((await self.control.heartbeat(run_id, worker, index)).active)
                self.assertIsNone((await self.control.claim('other-worker'))['run'])
            for old_claim, old_worker in previous:
                await self.rejected(self.emit(old_claim, old_worker, index, text='stale'))
                await self.rejected(self.report(old_claim, old_worker))
            await self.emit(claim, worker, index)
            await self.emit(claim, worker, index)  # Identical delivery stays idempotent.
            self.assertEqual([row.seq for row in self.events(run_id)], list(range(1, index + 1)))
            previous.append((claim, worker))
            if index < 3:
                self.expire_lease()
        await self.report(claim, worker, text='worker-c result')
        for old_claim, old_worker in previous[:-1]:
            await self.rejected(self.report(old_claim, old_worker, text='overwrite'))
        run = self.session.get(RunRow, run_id)
        self.assertEqual(run.report_json['result']['final_text'], 'worker-c result')
        self.assertIsNone((await self.control.claim('other-worker'))['run'])

    async def test_terminal_report_seals_event_store(self):
        claim = await self.control.claim('worker-a')
        await self.emit(claim, 'worker-a', 1)
        await self.report(claim, 'worker-a')
        await self.report(claim, 'worker-a')  # Existing report retry is harmless.
        await self.rejected(self.emit(claim, 'worker-a', 2))
        await self.rejected(self.report(claim, 'worker-a', text='conflicting result'))
        self.assertEqual([row.seq for row in self.events(claim['run']['run_id'])], [1])

    async def test_failed_run_retry_has_fresh_sequence_and_preserves_old_events(self):
        first = await self.control.claim('worker-a')
        await self.emit(first, 'worker-a', 1)
        await self.report(first, 'worker-a', status='failed')
        await self.report(first, 'worker-a', status='failed')
        self.assertIsNone((await self.control.claim('worker-b'))['run'])
        self.now += timedelta(seconds=3)
        retry = await self.control.claim('worker-b')
        self.assertNotEqual(retry['run']['run_id'], first['run']['run_id'])
        self.assertEqual((retry['event_seq'], retry['lease_token']), (0, 1))
        await self.execute(retry, 'worker-b')
        self.assertEqual([row.seq for row in self.events(first['run']['run_id'])], [1])
        self.assertEqual(self.events(retry['run']['run_id'])[0].seq, 1)
        self.assertEqual(self.session.get(TaskRow, self.task.task_id).status, 'completed')

    async def test_cancel_intent_survives_takeover(self):
        first = await self.control.claim('worker-a')
        await self.emit(first, 'worker-a', 1)
        await repository.request_cancel(self.db, self.task.task_id, 'owner')
        self.expire_lease()
        second = await self.control.claim('worker-b')
        heartbeat = await self.control.heartbeat(second['run']['run_id'], 'worker-b', 2)
        self.assertTrue(heartbeat.active)
        self.assertTrue(heartbeat.cancel_requested)
        await self.report(second, 'worker-b', status='cancelled')
        self.assertEqual(self.session.get(TaskRow, self.task.task_id).status, 'cancelled')
        self.assertIsNone((await self.control.claim('other-worker'))['run'])


if __name__ == '__main__':
    unittest.main()
