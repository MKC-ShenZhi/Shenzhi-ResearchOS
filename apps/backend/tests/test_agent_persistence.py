"""Contract tests for PostgreSQL Agent session persistence (requires CHAT_DATABASE_URL)."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.exc import StatementError

from app.core.worker_lease import run_with_heartbeat
from app.core.errors import BusinessError
from app.core.database import session_scope
from app.models.agent_session import AgentTurnRow
from app.services.agent_sessions.postgres_repository import PostgresAgentSessionRepository


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class PostgresAgentClaimTests(unittest.IsolatedAsyncioTestCase):
    SOURCE = 'anon:00000000-0000-4000-8000-000000000001'
    TARGET = 'user:a'

    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        self.repo = PostgresAgentSessionRepository()
        await self.repo.purge_owner(self.SOURCE)
        await self.repo.purge_owner(self.TARGET)

    async def asyncTearDown(self):
        from app.core.database import dispose_engine
        await self.repo.purge_owner(self.SOURCE)
        await self.repo.purge_owner(self.TARGET)
        await self.repo.close()
        await dispose_engine()

    async def test_claim_is_restricted_to_prepared_session_ids(self):
        prepared = await self.repo.create(self.SOURCE, 'prepared', {})
        not_prepared = await self.repo.create(self.SOURCE, 'not prepared', {})

        result = await self.repo.claim_anonymous_sessions(
            self.SOURCE, self.TARGET, session_ids=[prepared.id]
        )

        self.assertEqual(result['moved_session_ids'], [prepared.id])
        self.assertEqual((await self.repo.get(prepared.id, self.TARGET)).owner, self.TARGET)
        self.assertEqual(
            (await self.repo.get(not_prepared.id, self.SOURCE)).owner, self.SOURCE
        )

    async def test_claim_rechecks_running_state_after_prepare(self):
        session = await self.repo.create(self.SOURCE, 'becomes running', {})
        prepared_ids = await self.repo.claimable_session_ids(self.SOURCE)
        self.assertIn(session.id, prepared_ids)
        await self.repo.start_turn(
            session.id, self.SOURCE, 'run', {}, [], worker_id='worker-a',
        )

        result = await self.repo.claim_anonymous_sessions(
            self.SOURCE, self.TARGET, session_ids=prepared_ids
        )

        self.assertEqual(result['moved_session_ids'], [])
        self.assertEqual(result['skipped_running_count'], 1)
        self.assertEqual((await self.repo.get(session.id, self.SOURCE)).owner, self.SOURCE)

    async def test_concurrent_agent_idempotency_reuses_turn_and_distinct_key_creates_new_turn(self):
        session = await self.repo.create(self.SOURCE, 'question', {})
        fingerprint = 'fingerprint-for-same-request'
        start = lambda key: self.repo.start_turn(
            session.id, self.SOURCE, 'same request', {}, [],
            worker_id='worker-a',
            idempotency_key=key, idempotency_fingerprint=fingerprint,
        )

        first, second = await asyncio.gather(start('agent-pg-operation'), start('agent-pg-operation'))
        self.assertEqual(first[0].id, second[0].id)
        self.assertEqual(sorted((first[1], second[1])), [False, True])

        with self.assertRaises(BusinessError) as conflict:
            await self.repo.start_turn(
                session.id, self.SOURCE, 'different request', {}, [],
                worker_id='worker-a',
                idempotency_key='agent-pg-operation',
                idempotency_fingerprint='fingerprint-for-different-request',
            )
        self.assertEqual(conflict.exception.status, 409)

        await self.repo.finish_turn(
            session.id, self.SOURCE, first[0].id,
            {'status': 'done', 'assistant_content': 'answer'}, worker_id='worker-a',
        )
        another = await start('agent-pg-operation-2')
        self.assertTrue(another[1])
        self.assertNotEqual(first[0].id, another[0].id)
        detail = await self.repo.get(session.id, self.SOURCE)
        self.assertEqual(len(detail.turns), 2)

    async def test_failed_agent_turn_insert_can_retry_same_idempotency_key(self):
        session = await self.repo.create(self.SOURCE, 'question', {})

        with self.assertRaises((TypeError, StatementError)):
            await self.repo.start_turn(
                session.id, self.SOURCE, 'same request', {'invalid': object()}, [],
                worker_id='worker-a',
                idempotency_key='agent-pg-failed-operation',
                idempotency_fingerprint='same-request',
            )

        turn, created = await self.repo.start_turn(
            session.id, self.SOURCE, 'same request', {}, [],
            worker_id='worker-a',
            idempotency_key='agent-pg-failed-operation',
            idempotency_fingerprint='same-request',
        )
        self.assertTrue(created)
        detail = await self.repo.get(session.id, self.SOURCE)
        self.assertEqual([item.id for item in detail.turns], [turn.id])

    async def test_agent_recovery_preserves_another_workers_live_lease(self):
        session = await self.repo.create(self.SOURCE, 'live', {})
        turn, created = await self.repo.start_turn(
            session.id, self.SOURCE, 'live task', {}, [], worker_id='worker-a',
        )
        self.assertTrue(created)
        other_worker = PostgresAgentSessionRepository()

        await other_worker.recover()

        async with session_scope() as db:
            row = await db.get(AgentTurnRow, turn.id)
        self.assertEqual(row.status, 'running')
        self.assertEqual(row.worker_id, 'worker-a')
        self.assertGreater(row.lease_expires_at, datetime.now(timezone.utc))

    async def test_agent_get_recovers_expired_lease_without_worker_restart(self):
        session = await self.repo.create(self.SOURCE, 'expired', {})
        turn, _ = await self.repo.start_turn(
            session.id, self.SOURCE, 'stale task', {}, [], worker_id='worker-a',
            idempotency_key='agent-expired-operation',
            idempotency_fingerprint='same-request',
        )
        async with session_scope() as db:
            await db.execute(
                update(AgentTurnRow).where(AgentTurnRow.id == turn.id)
                .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )

        worker_b = PostgresAgentSessionRepository()
        recovered = await worker_b.get(session.id, self.SOURCE)

        self.assertEqual(recovered.turns[0].id, turn.id)
        self.assertEqual(recovered.turns[0].status, 'failed')
        with self.assertRaises(BusinessError):
            await self.repo.finish_turn(
                session.id, self.SOURCE, turn.id,
                {'status': 'done', 'assistant_content': 'stale answer'}, worker_id='worker-a',
            )
        replay, created = await worker_b.start_turn(
            session.id, self.SOURCE, 'stale task', {}, [], worker_id='worker-b',
            idempotency_key='agent-expired-operation',
            idempotency_fingerprint='same-request',
        )
        self.assertFalse(created)
        self.assertEqual(replay.id, turn.id)

    async def test_agent_heartbeat_renews_without_model_output(self):
        session = await self.repo.create(self.SOURCE, 'quiet model', {})
        turn, _ = await self.repo.start_turn(
            session.id, self.SOURCE, 'quiet task', {}, [], worker_id='worker-a',
        )
        initial = await self.repo.get(session.id, self.SOURCE)
        initial_lease = initial.turns[0].lease_expires_at
        model_wait = asyncio.Event()
        task = asyncio.create_task(run_with_heartbeat(
            model_wait.wait,
            lambda: self.repo.renew_turn(turn.id, 'worker-a'),
            interval_seconds=0.01,
        ))

        await asyncio.sleep(0.05)
        renewed = await self.repo.get(session.id, self.SOURCE)
        self.assertFalse(task.done())
        self.assertGreater(renewed.turns[0].lease_expires_at, initial_lease)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_expired_agent_lease_recovers_and_old_worker_cannot_finish(self):
        session = await self.repo.create(self.SOURCE, 'expired', {})
        turn, _ = await self.repo.start_turn(
            session.id, self.SOURCE, 'stale task', {}, [], worker_id='worker-a',
        )
        async with session_scope() as db:
            await db.execute(
                update(AgentTurnRow).where(AgentTurnRow.id == turn.id)
                .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
        other_worker = PostgresAgentSessionRepository()

        await other_worker.recover()

        with self.assertRaises(BusinessError):
            await self.repo.finish_turn(
                session.id, self.SOURCE, turn.id,
                {'status': 'done', 'assistant_content': 'stale answer'}, worker_id='worker-a',
            )
        async with session_scope() as db:
            row = await db.get(AgentTurnRow, turn.id)
        self.assertEqual(row.status, 'failed')

    async def test_agent_renewal_and_recovery_are_serialized(self):
        session = await self.repo.create(self.SOURCE, 'race', {})
        turn, _ = await self.repo.start_turn(
            session.id, self.SOURCE, 'race task', {}, [], worker_id='worker-a',
        )
        other_worker = PostgresAgentSessionRepository()

        renewed, _ = await asyncio.gather(
            self.repo.renew_turn(turn.id, 'worker-a'), other_worker.recover(),
        )

        async with session_scope() as db:
            row = await db.get(AgentTurnRow, turn.id)
        self.assertTrue(renewed)
        self.assertEqual(row.status, 'running')
        self.assertEqual(row.worker_id, 'worker-a')
        self.assertGreater(row.lease_expires_at, datetime.now(timezone.utc))


    async def test_agent_shutdown_releases_only_own_worker_leases(self):
        from app.core.worker_lease import current_worker_id

        own_session = await self.repo.create(self.SOURCE, 'own', {})
        own, _ = await self.repo.start_turn(
            own_session.id, self.SOURCE, 'own task', {}, [], worker_id=current_worker_id(),
        )
        other_session = await self.repo.create(self.SOURCE, 'other', {})
        other, _ = await self.repo.start_turn(
            other_session.id, self.SOURCE, 'other task', {}, [], worker_id='worker-a',
        )

        await PostgresAgentSessionRepository().close()

        async with session_scope() as db:
            own_row = await db.get(AgentTurnRow, own.id)
            other_row = await db.get(AgentTurnRow, other.id)
        self.assertEqual((own_row.status, own_row.stop_reason), ('failed', 'backend_restart'))
        self.assertIsNone(own_row.lease_expires_at)
        self.assertEqual((other_row.status, other_row.worker_id), ('running', 'worker-a'))
        _, created = await self.repo.start_turn(
            own_session.id, self.SOURCE, 'after restart', {}, [], worker_id='worker-b',
        )
        self.assertTrue(created)

if __name__ == '__main__':
    unittest.main()
