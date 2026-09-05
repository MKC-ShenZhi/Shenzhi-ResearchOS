"""Contract tests for PostgreSQL session persistence (requires CHAT_DATABASE_URL)."""
import asyncio
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.errors import BusinessError
from app.core.database import session_scope
from app.models.chat import ChatMessageRow, ChatSessionRow
from app.services.postgres_sessions import PostgresSessionRepository
from app.services.sessions import MemorySessionRepository


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

    async def test_streaming_recover_marks_failed(self):
        session = await self.repo.create('user:a', 'q', {'type': 'ask', 'mode': 'fast', 'model': 'm', 'web_search': False})
        message = await self.repo.add_message(session, 'q', session.settings)
        message.content = 'partial'
        await self.repo.recover()
        restored = await self.repo.get(session.id, 'user:a')
        self.assertEqual(restored.messages[0].status, 'failed')
        self.assertEqual(restored.messages[0].content, 'partial')

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


if __name__ == '__main__':
    unittest.main()
