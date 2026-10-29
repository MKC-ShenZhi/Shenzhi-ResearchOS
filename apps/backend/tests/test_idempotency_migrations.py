"""Destructive 014 <-> 016 roundtrip ONLY in an explicitly supplied empty local test database.

Run with SHENZHI_MIGRATION_TEST_URL pointing at a disposable *_migration_test
PostgreSQL database. Never uses CHAT_DATABASE_URL implicitly.
"""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import unittest

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_URL = os.getenv('SHENZHI_MIGRATION_TEST_URL', '')
SESSION_ID = '00000000-0000-4000-8000-0000000000a1'
STREAMING_ID = '00000000-0000-4000-8000-0000000000b1'
DONE_ID = '00000000-0000-4000-8000-0000000000b2'
CHAT_COLUMNS = {
    'idempotency_owner', 'idempotency_scope', 'idempotency_key', 'idempotency_fingerprint',
    'worker_id', 'lease_expires_at', 'generation_claimed',
}
AGENT_COLUMNS = {'idempotency_key', 'idempotency_fingerprint', 'worker_id', 'lease_expires_at'}


@unittest.skipUnless(MIGRATION_URL, 'SHENZHI_MIGRATION_TEST_URL not set (disposable local database required)')
class IdempotencyMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_in_flight_rows_and_downgrade_restores_014(self):
        url = make_url(MIGRATION_URL)
        self.assertIn(url.host, ('127.0.0.1', 'localhost', '::1'))
        self.assertTrue((url.database or '').endswith('_migration_test'))
        async_url = url.set(drivername='postgresql+asyncpg')

        async def run(callback):
            engine = create_async_engine(async_url)
            try:
                async with engine.begin() as connection:
                    return await callback(connection)
            finally:
                await engine.dispose()

        def alembic(*args):
            result = subprocess.run(
                [sys.executable, '-m', 'alembic', *args], cwd=ROOT,
                env={**os.environ, 'CHAT_DATABASE_URL': MIGRATION_URL},
                text=True, capture_output=True, check=True,
            )
            return result.stdout + result.stderr

        async def tables(connection):
            return await connection.run_sync(lambda conn: inspect(conn).get_table_names())

        # Refuse to destroy any previously populated database, even a test one.
        self.assertEqual(asyncio.run(run(tables)), [], 'Migration roundtrip requires an EMPTY test database')
        heads = alembic('heads')
        self.assertEqual(heads.count('(head)'), 1)
        self.assertIn('016_request_idempotency (head)', heads)
        self.assertIn('014_platform_snapshots -> 016_request_idempotency', alembic('history'))

        alembic('upgrade', '014_platform_snapshots')

        async def seed(connection):
            await connection.execute(text(
                "INSERT INTO chat_sessions(id, owner, title, settings, favorite) "
                "VALUES (:id, 'user:migration', 'seed', '{}'::jsonb, false)"
            ), {'id': SESSION_ID})
            for message_id, status in ((STREAMING_ID, 'streaming'), (DONE_ID, 'done')):
                await connection.execute(text(
                    "INSERT INTO chat_messages(id, session_id, question, settings, status, content) "
                    "VALUES (:id, :session_id, 'q', '{}'::jsonb, :status, 'partial')"
                ), {'id': message_id, 'session_id': SESSION_ID, 'status': status})
            await connection.execute(text(
                "INSERT INTO agent_sessions(id, owner, title, settings) "
                "VALUES ('agent-migration', 'user:migration', 'seed', '{}'::jsonb)"
            ))
            await connection.execute(text(
                "INSERT INTO agent_turns(id, session_id, user_content, settings, status) "
                "VALUES ('turn-migration', 'agent-migration', 'run', '{}'::jsonb, 'running')"
            ))

        asyncio.run(run(seed))
        alembic('upgrade', 'head')
        self.assertIn('016_request_idempotency', alembic('current'))

        async def check_upgraded(connection):
            chat_columns = {item['name'] for item in await connection.run_sync(
                lambda conn: inspect(conn).get_columns('chat_messages'))}
            agent_columns = {item['name'] for item in await connection.run_sync(
                lambda conn: inspect(conn).get_columns('agent_turns'))}
            self.assertTrue(CHAT_COLUMNS <= chat_columns)
            self.assertTrue(AGENT_COLUMNS <= agent_columns)
            indexes = {row.indexname: row.indexdef for row in await connection.execute(text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE indexname IN ('uq_chat_messages_idempotency', 'uq_agent_turns_idempotency')"
            ))}
            self.assertEqual(len(indexes), 2)
            for definition in indexes.values():
                self.assertIn('UNIQUE', definition)
                self.assertIn('idempotency_key IS NOT NULL', definition)

            rows = {str(row.id): row for row in await connection.execute(text(
                "SELECT id, status, content, generation_claimed, worker_id, "
                "lease_expires_at - clock_timestamp() AS remaining FROM chat_messages"
            ))}
            legacy = rows[STREAMING_ID]
            # In-flight legacy work is claimed by an unknown worker for a grace period.
            self.assertEqual((legacy.status, legacy.content, legacy.generation_claimed),
                             ('streaming', 'partial', True))
            self.assertIsNone(legacy.worker_id)
            self.assertGreater(legacy.remaining.total_seconds(), 9 * 60)
            done = rows[DONE_ID]
            self.assertEqual((done.status, done.generation_claimed), ('done', False))
            self.assertIsNone(done.remaining)
            turn = (await connection.execute(text(
                "SELECT status, lease_expires_at > clock_timestamp() AS leased FROM agent_turns"
            ))).one()
            self.assertEqual((turn.status, turn.leased), ('running', True))

            # The partial unique index rejects a reused key but allows unkeyed rows.
            await connection.execute(text(
                "UPDATE chat_messages SET idempotency_owner = 'user:migration', "
                "idempotency_scope = 'chat:create', idempotency_key = 'same' WHERE id = :id"
            ), {'id': DONE_ID})

        asyncio.run(run(check_upgraded))

        async def duplicate_key(connection):
            await connection.execute(text(
                "UPDATE chat_messages SET idempotency_owner = 'user:migration', "
                "idempotency_scope = 'chat:create', idempotency_key = 'same' WHERE id = :id"
            ), {'id': STREAMING_ID})

        with self.assertRaises(Exception) as caught:
            asyncio.run(run(duplicate_key))
        self.assertIn('uq_chat_messages_idempotency', str(caught.exception))

        alembic('downgrade', '014_platform_snapshots')

        async def check_downgraded(connection):
            chat_columns = {item['name'] for item in await connection.run_sync(
                lambda conn: inspect(conn).get_columns('chat_messages'))}
            agent_columns = {item['name'] for item in await connection.run_sync(
                lambda conn: inspect(conn).get_columns('agent_turns'))}
            self.assertTrue(CHAT_COLUMNS.isdisjoint(chat_columns))
            self.assertTrue(AGENT_COLUMNS.isdisjoint(agent_columns))
            count = await connection.scalar(text(
                "SELECT count(*) FROM chat_messages WHERE session_id = :id"
            ), {'id': SESSION_ID})
            self.assertEqual(count, 2)

        asyncio.run(run(check_downgraded))
        self.assertIn('014_platform_snapshots', alembic('current'))
        alembic('upgrade', 'head')
        self.assertIn('016_request_idempotency', alembic('current'))


if __name__ == '__main__':
    unittest.main()
