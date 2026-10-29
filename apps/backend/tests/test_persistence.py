"""Contract tests for PostgreSQL session persistence (requires CHAT_DATABASE_URL)."""
import asyncio
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import select, update
from sqlalchemy.exc import StatementError

from app.core.worker_lease import run_with_heartbeat
from app.core.errors import BusinessError
from app.core.database import session_scope
from app.models.agent_session import AgentTurnRow
from app.models.chat import ChatMessageRow, ChatSessionRow
from app.services.agent_sessions.postgres_repository import PostgresAgentSessionRepository
from app.services.chat.postgres_repository import PostgresSessionRepository
from app.services.chat.repository import MemorySessionRepository


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class PostgresPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        self.repo = PostgresSessionRepository()
        for owner in ('user:a', 'user:b', 'anon:00000000-0000-4000-8000-000000000001',
                      'anon:00000000-0000-4000-8000-000000000002'):
            await self.repo.purge_owner(owner)

    async def asyncTearDown(self):
        for owner in ('user:a', 'user:b', 'anon:00000000-0000-4000-8000-000000000001',
                      'anon:00000000-0000-4000-8000-000000000002'):
            await self.repo.purge_owner(owner)
        await self.repo.close()

    async def test_owner_isolation_and_restart_recovery(self):
        session = await self.repo.create('user:a', 'hello', {'type': 'ask', 'mode': 'fast', 'model': 'm', 'web_search': False})
        message = await self.repo.add_message(session, 'hello', session.settings)
        message.content, message.status = 'answer', 'done'
        await self.repo.persist_message(message)

        other = await self.repo.list('user:b')
        self.assertEqual(other, [])
        rows = await self.repo.list('user:a')
        self.assertEqual(len(rows), 1)

        detail = await self.repo.get(session.id, 'user:a')
        self.assertEqual(detail.messages[0].content, 'answer')
        with self.assertRaises(BusinessError) as caught:
            await self.repo.get(session.id, 'user:b')
        self.assertEqual(caught.exception.status, 404)

    async def test_concurrent_idempotent_chat_create_is_one_atomic_resource(self):
        body = {'question': '同一逻辑操作'}
        fingerprint = 'fingerprint-for-same-request'
        create = lambda: self.repo.create_with_message(
            'user:a', body['question'], {'mode': 'fast'}, '', [],
            scope='chat:create', key='chat-pg-operation', fingerprint=fingerprint,
        )

        first, second = await asyncio.gather(create(), create())

        self.assertEqual((first.id, first.session_id), (second.id, second.session_id))
        async with session_scope() as db:
            sessions = await db.scalars(select(ChatSessionRow).where(ChatSessionRow.owner == 'user:a'))
            messages = await db.scalars(select(ChatMessageRow).where(ChatMessageRow.session_id == uuid.UUID(first.session_id)))
        self.assertEqual(len(sessions.all()), 1)
        self.assertEqual(len(messages.all()), 1)

        distinct = await self.repo.create_with_message(
            'user:a', body['question'], {'mode': 'fast'}, '', [],
            scope='chat:create', key='chat-pg-operation-2', fingerprint=fingerprint,
        )
        self.assertNotEqual((first.id, first.session_id), (distinct.id, distinct.session_id))

        with self.assertRaises(BusinessError) as conflict:
            await self.repo.create_with_message(
                'user:a', 'different body', {'mode': 'fast'}, '', [],
                scope='chat:create', key='chat-pg-operation',
                fingerprint='fingerprint-for-different-request',
            )
        self.assertEqual(conflict.exception.status, 409)

    async def test_failed_idempotent_chat_create_can_retry_same_key(self):
        with self.assertRaises((TypeError, StatementError)):
            await self.repo.create_with_message(
                'user:a', 'same operation', {'invalid': object()}, '', [],
                scope='chat:create', key='chat-pg-failed-operation', fingerprint='same-request',
            )

        retried = await self.repo.create_with_message(
            'user:a', 'same operation', {'mode': 'fast'}, '', [],
            scope='chat:create', key='chat-pg-failed-operation', fingerprint='same-request',
        )
        async with session_scope() as db:
            sessions = await db.scalars(select(ChatSessionRow).where(ChatSessionRow.owner == 'user:a'))
            messages = await db.scalars(select(ChatMessageRow).where(
                ChatMessageRow.session_id == uuid.UUID(retried.session_id),
            ))
        self.assertEqual(len(sessions.all()), 1)
        self.assertEqual(len(messages.all()), 1)

    async def test_concurrent_idempotent_followup_reuses_message_and_new_key_creates_message(self):
        session = await self.repo.create('user:a', 'question', {'mode': 'fast'})
        fingerprint = 'same-followup-request'

        async def add(key):
            return await self.repo.add_message(
                session, 'follow up', session.settings,
                idempotency_owner='user:a',
                idempotency_scope=f'chat:session:{session.id}:message',
                idempotency_key=key,
                idempotency_fingerprint=fingerprint,
            )

        first, duplicate = await asyncio.gather(add('followup-operation'), add('followup-operation'))
        self.assertEqual(first.id, duplicate.id)
        first.status = 'done'
        await self.repo.persist_message(first)

        distinct = await add('followup-operation-2')
        self.assertNotEqual(first.id, distinct.id)
        detail = await self.repo.get(session.id, 'user:a')
        self.assertEqual(len(detail.messages), 2)

    async def test_concurrent_chat_stream_claim_has_one_generator_owner(self):
        session = await self.repo.create('user:a', 'once', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'once', session.settings)

        first, second = await asyncio.gather(
            self.repo.claim_generation(message, 'worker-a'),
            self.repo.claim_generation(message, 'worker-b'),
        )

        self.assertEqual(sorted((first, second)), [False, True])
        restored = await self.repo.get(session.id, 'user:a')
        self.assertTrue(restored.messages[0].generation_claimed)

    async def test_failed_chat_claim_refreshes_cached_message_after_remote_completion(self):
        session = await self.repo.create('user:a', 'once', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'once', session.settings)
        self.assertTrue(await self.repo.claim_generation(message))

        async with session_scope() as db:
            await db.execute(
                update(ChatMessageRow)
                .where(ChatMessageRow.id == uuid.UUID(message.id))
                .values(status='done', content='remote result', reasoning='remote reasoning',
                        message_refs=[{'title': 'source'}], followups=['next'], duration_ms=10)
            )

        self.assertFalse(await self.repo.claim_generation(message))
        self.assertEqual(message.status, 'done')
        self.assertEqual(message.content, 'remote result')
        self.assertEqual(message.reasoning, 'remote reasoning')
        self.assertEqual(message.references, [{'title': 'source'}])
        self.assertEqual(message.followups, ['next'])

    async def test_streaming_recover_marks_failed(self):
        session = await self.repo.create('user:a', 'q', {'type': 'ask', 'mode': 'fast', 'model': 'm', 'web_search': False})
        message = await self.repo.add_message(session, 'q', session.settings)
        message.content = 'partial'
        self.assertTrue(await self.repo.claim_generation(message, 'worker-a'))
        async with session_scope() as db:
            await db.execute(
                update(ChatMessageRow)
                .where(ChatMessageRow.id == uuid.UUID(message.id))
                .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
        await self.repo.recover()
        restored = await self.repo.get(session.id, 'user:a')
        self.assertEqual(restored.messages[0].status, 'failed')
        self.assertEqual(restored.messages[0].content, 'partial')
        message.content, message.status = 'stale answer', 'done'
        self.assertFalse(await self.repo.persist_message(message, 'worker-a'))
        async with session_scope() as db:
            row = await db.get(ChatMessageRow, uuid.UUID(message.id))
        self.assertEqual(row.status, 'failed')

    async def test_chat_recovery_preserves_another_workers_live_lease(self):
        session = await self.repo.create('user:a', 'live', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'live', session.settings)
        self.assertTrue(await self.repo.claim_generation(message, 'worker-a'))
        other_worker = PostgresSessionRepository()

        await other_worker.recover()

        async with session_scope() as db:
            row = await db.get(ChatMessageRow, uuid.UUID(message.id))
        self.assertEqual(row.status, 'streaming')
        self.assertEqual(row.worker_id, 'worker-a')
        self.assertGreater(row.lease_expires_at, datetime.now(timezone.utc))

    async def test_chat_claim_respects_transition_lease_from_previous_version(self):
        session = await self.repo.create('user:a', 'legacy live', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'legacy live', session.settings)
        transition_lease = datetime.now(timezone.utc) + timedelta(minutes=10)
        async with session_scope() as db:
            await db.execute(
                update(ChatMessageRow)
                .where(ChatMessageRow.id == uuid.UUID(message.id))
                .values(lease_expires_at=transition_lease)
            )

        claimed = await PostgresSessionRepository().claim_generation(message, 'worker-b')

        self.assertFalse(claimed)
        async with session_scope() as db:
            row = await db.get(ChatMessageRow, uuid.UUID(message.id))
        self.assertFalse(row.generation_claimed)
        self.assertIsNone(row.worker_id)
        self.assertGreater(row.lease_expires_at, datetime.now(timezone.utc))

    async def test_chat_get_recovers_expired_lease_without_worker_restart(self):
        session = await self.repo.create('user:a', 'expired', {'mode': 'fast'})
        scope = f'chat:session:{session.id}:message'
        message = await self.repo.add_message(
            session, 'expired', session.settings, idempotency_owner='user:a',
            idempotency_scope=scope, idempotency_key='chat-expired-operation',
            idempotency_fingerprint='same-request',
        )
        self.assertTrue(await self.repo.claim_generation(message, 'worker-a'))
        async with session_scope() as db:
            await db.execute(
                update(ChatMessageRow).where(ChatMessageRow.id == uuid.UUID(message.id))
                .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )

        worker_b = PostgresSessionRepository()
        recovered = await worker_b.get(session.id, 'user:a')

        self.assertEqual(recovered.messages[0].status, 'failed')
        self.assertEqual(recovered.messages[0].worker_id, None)
        replay = await worker_b.find_idempotent_message(
            'user:a', scope, 'chat-expired-operation', 'same-request',
        )
        self.assertIsNotNone(replay)
        self.assertEqual(replay.id, message.id)
        self.assertEqual(replay.status, 'failed')
        message.content, message.status = 'stale answer', 'done'
        self.assertFalse(await self.repo.persist_message(message, 'worker-a'))
        next_message = await worker_b.add_message(
            recovered, 'new operation', recovered.settings,
            idempotency_owner='user:a', idempotency_scope=f'chat:session:{session.id}:message',
            idempotency_key='chat-after-expired-lease',
            idempotency_fingerprint='new-request',
        )
        self.assertEqual(next_message.status, 'streaming')

    async def test_chat_stop_on_another_worker_cannot_write_terminal_state(self):
        session = await self.repo.create('user:a', 'active', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'active', session.settings)
        self.assertTrue(await self.repo.claim_generation(message, 'worker-a'))
        worker_b = PostgresSessionRepository()
        remote_message = await worker_b.message(message.id, 'user:a')

        from app.services.chat.service import stop_message

        with patch('app.services.chat.service.repository', worker_b):
            with self.assertRaises(BusinessError) as caught:
                await stop_message(remote_message)

        self.assertEqual(caught.exception.status, 409)
        async with session_scope() as db:
            row = await db.get(ChatMessageRow, uuid.UUID(message.id))
        self.assertEqual(row.status, 'streaming')
        self.assertEqual(row.worker_id, 'worker-a')

        unclaimed_session = await self.repo.create('user:a', 'not claimed', {'mode': 'fast'})
        unclaimed_message = await self.repo.add_message(
            unclaimed_session, 'not claimed', unclaimed_session.settings,
        )
        with patch('app.services.chat.service.repository', worker_b):
            await stop_message(unclaimed_message)
        async with session_scope() as db:
            unclaimed_row = await db.get(ChatMessageRow, uuid.UUID(unclaimed_message.id))
        self.assertEqual(unclaimed_row.status, 'stopped')

    async def test_chat_remote_terminal_stream_replays_when_worker_cursor_is_unavailable(self):
        session = await self.repo.create('user:a', 'completed remotely', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'completed remotely', session.settings)
        self.assertTrue(await self.repo.claim_generation(message, 'worker-a'))
        worker_b = PostgresSessionRepository()
        await worker_b.message(message.id, 'user:a')

        message.content, message.status = 'persisted final answer', 'done'
        self.assertTrue(await self.repo.persist_message(message, 'worker-a'))

        from app.api.chat import stream

        with patch('app.api.chat.repository', worker_b):
            response = await stream(message.id, 'user:a', '17')
        chunks = [chunk async for chunk in response.body_iterator]
        body = ''.join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

        self.assertIn('persisted final answer', body)
        self.assertIn('event: done', body)

    async def test_chat_heartbeat_renews_without_model_output(self):
        session = await self.repo.create('user:a', 'quiet model', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'quiet model', session.settings)
        self.assertTrue(await self.repo.claim_generation(message, 'worker-a'))
        initial_lease = message.lease_expires_at
        model_wait = asyncio.Event()
        task = asyncio.create_task(run_with_heartbeat(
            model_wait.wait,
            lambda: self.repo.renew_generation(message.id, 'worker-a'),
            interval_seconds=0.01,
        ))

        await asyncio.sleep(0.05)
        async with session_scope() as db:
            row = await db.get(ChatMessageRow, uuid.UUID(message.id))
        self.assertFalse(task.done())
        self.assertGreater(row.lease_expires_at, initial_lease)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_chat_renewal_and_recovery_are_serialized(self):
        session = await self.repo.create('user:a', 'race', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'race', session.settings)
        self.assertTrue(await self.repo.claim_generation(message, 'worker-a'))
        other_worker = PostgresSessionRepository()

        renewed, _ = await asyncio.gather(
            self.repo.renew_generation(message.id, 'worker-a'), other_worker.recover(),
        )

        async with session_scope() as db:
            row = await db.get(ChatMessageRow, uuid.UUID(message.id))
        self.assertTrue(renewed)
        self.assertEqual(row.status, 'streaming')
        self.assertEqual(row.worker_id, 'worker-a')
        self.assertGreater(row.lease_expires_at, datetime.now(timezone.utc))

    async def test_finalize_is_idempotent(self):
        session = await self.repo.create('user:a', 'q', {'type': 'ask', 'mode': 'fast', 'model': 'm', 'web_search': False})
        message = await self.repo.add_message(session, 'q', session.settings)
        message.content, message.status = 'done text', 'done'
        await self.repo.persist_message(message)
        message.content = 'overwrite'
        await self.repo.persist_message(message)
        async with session_scope() as db:
            row = await db.scalar(select(ChatMessageRow).where(ChatMessageRow.id == uuid.UUID(message.id)))
        assert row is not None
        self.assertEqual(row.content, 'done text')

    async def test_claim_moves_completed_sessions_and_skips_streaming(self):
        source = 'anon:00000000-0000-4000-8000-000000000001'
        other = 'anon:00000000-0000-4000-8000-000000000002'
        completed = await self.repo.create(source, 'done', {'mode': 'fast'})
        completed_message = await self.repo.add_message(completed, 'done', completed.settings)
        completed_message.content, completed_message.status = 'answer', 'done'
        await self.repo.persist_message(completed_message)
        streaming = await self.repo.create(source, 'streaming', {'mode': 'fast'})
        streaming_message = await self.repo.add_message(streaming, 'streaming', streaming.settings)
        await self.repo.create(other, 'other browser', {'mode': 'fast'})

        result = await self.repo.claim_anonymous_sessions(source, 'user:a')
        self.assertEqual(result, {
            'moved_count': 1,
            'skipped_streaming_count': 1,
            'durable': True,
        })
        claimed = await self.repo.get(completed.id, 'user:a')
        self.assertEqual(claimed.messages[0].id, completed_message.id)
        self.assertEqual(claimed.messages[0].content, 'answer')
        self.assertEqual((await self.repo.get(streaming.id, source)).owner, source)
        self.assertEqual(len(await self.repo.list(other)), 1)
        streaming_message.content, streaming_message.status = 'finished later', 'done'
        await self.repo.persist_message(streaming_message)
        retry = await self.repo.claim_anonymous_sessions(source, 'user:a')
        self.assertEqual(retry, {
            'moved_count': 1,
            'skipped_streaming_count': 0,
            'durable': True,
        })
        self.assertEqual((await self.repo.get(streaming.id, 'user:a')).messages[0].content,
                         'finished later')
        self.assertEqual(
            await self.repo.claim_anonymous_sessions(source, 'user:a'),
            {'moved_count': 0, 'skipped_streaming_count': 0, 'durable': True},
        )

    async def test_concurrent_claim_is_idempotent(self):
        source = 'anon:00000000-0000-4000-8000-000000000001'
        session = await self.repo.create(source, 'done', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'done', session.settings)
        message.status = 'done'
        await self.repo.persist_message(message)

        first, second = await asyncio.gather(
            self.repo.claim_anonymous_sessions(source, 'user:a'),
            self.repo.claim_anonymous_sessions(source, 'user:a'),
        )
        self.assertEqual(sorted((first['moved_count'], second['moved_count'])), [0, 1])
        self.assertEqual(len(await self.repo.list('user:a')), 1)

    async def test_purge_expired_anonymous_sessions_keeps_users_and_recent_rows(self):
        expired = await self.repo.create('anon:00000000-0000-4000-8000-000000000001', 'expired', {'mode': 'fast'})
        expired_message = await self.repo.add_message(expired, 'expired', expired.settings)
        expired_message.status = 'done'
        await self.repo.persist_message(expired_message)
        recent = await self.repo.create('anon:00000000-0000-4000-8000-000000000002', 'recent', {'mode': 'fast'})
        user = await self.repo.create('user:a', 'user', {'mode': 'fast'})
        async with session_scope() as db:
            await db.execute(
                ChatSessionRow.__table__.update()
                .where(ChatSessionRow.id == uuid.UUID(expired.id))
                .values(updated_at=datetime.now(timezone.utc) - timedelta(days=8))
            )

        deleted = await self.repo.purge_expired_anonymous_sessions(
            datetime.now(timezone.utc) - timedelta(days=7)
        )
        self.assertEqual(deleted, 1)
        self.assertEqual(await self.repo.list('anon:00000000-0000-4000-8000-000000000001'), [])
        self.assertEqual(len(await self.repo.list('anon:00000000-0000-4000-8000-000000000002')), 1)
        self.assertEqual(len(await self.repo.list('user:a')), 1)
        async with session_scope() as db:
            self.assertIsNone(await db.scalar(select(ChatMessageRow).where(
                ChatMessageRow.id == uuid.UUID(expired_message.id)
            )))
        self.assertEqual(recent.owner, 'anon:00000000-0000-4000-8000-000000000002')
        self.assertEqual(user.owner, 'user:a')

    async def test_purge_expired_anonymous_sessions_keeps_active_streams(self):
        owner = 'anon:00000000-0000-4000-8000-000000000001'
        session = await self.repo.create(owner, 'active', {'mode': 'fast'})
        message = await self.repo.add_message(session, 'active', session.settings)
        async with session_scope() as db:
            await db.execute(
                ChatSessionRow.__table__.update()
                .where(ChatSessionRow.id == uuid.UUID(session.id))
                .values(updated_at=datetime.now(timezone.utc) - timedelta(days=8))
            )

        deleted = await self.repo.purge_expired_anonymous_sessions(
            datetime.now(timezone.utc) - timedelta(days=7)
        )
        self.assertEqual(deleted, 0)
        self.assertEqual((await self.repo.get(session.id, owner)).messages[0].id, message.id)


class MemoryRepositoryAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_wrapper_parity(self):
        repo = MemorySessionRepository()
        session = await repo.create('user:a', 'q', {'type': 'ask', 'mode': 'fast', 'model': 'm', 'web_search': False})
        message = await repo.add_message(session, 'q', session.settings)
        self.assertFalse(repo.is_durable)
        await repo.persist_message(message)
        listed = await repo.list('user:a')
        self.assertEqual(len(listed), 1)

    async def test_backend_restart_makes_old_memory_session_a_normal_404(self):
        old_repo = MemorySessionRepository()
        session = await old_repo.create('user:a', 'q', {'type': 'chat', 'mode': 'fast', 'model': 'm', 'web_search': False})
        restarted_repo = MemorySessionRepository()

        with self.assertRaises(BusinessError) as caught:
            await restarted_repo.get(session.id, 'user:a')

        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(caught.exception.message, '会话不存在或已过期')

    async def test_claim_never_reports_ephemeral_migration_as_durable(self):
        repo = MemorySessionRepository()
        await repo.create('anon:00000000-0000-4000-8000-000000000001', 'q', {'mode': 'fast'})
        result = await repo.claim_anonymous_sessions(
            'anon:00000000-0000-4000-8000-000000000001',
            'user:a',
        )
        self.assertEqual(result, {
            'moved_count': 0,
            'skipped_streaming_count': 0,
            'durable': False,
        })
        self.assertEqual(len(await repo.list('anon:00000000-0000-4000-8000-000000000001')), 1)

    async def test_memory_cleanup_is_explicit_noop(self):
        repo = MemorySessionRepository()
        self.assertEqual(await repo.purge_expired_anonymous_sessions(datetime.now(timezone.utc)), 0)


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
        await self.repo.purge_owner(self.SOURCE)
        await self.repo.purge_owner(self.TARGET)
        await self.repo.close()

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


if __name__ == '__main__':
    unittest.main()
