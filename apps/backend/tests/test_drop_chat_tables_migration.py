"""Destructive 020 <-> 021 roundtrip ONLY in an explicitly supplied empty local test database.

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


@unittest.skipUnless(MIGRATION_URL, 'SHENZHI_MIGRATION_TEST_URL not set (disposable local database required)')
class DropChatTablesMigrationTests(unittest.TestCase):
    def test_single_head_drops_chat_tables_and_downgrade_restores_empty_schema(self):
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
            return set(await connection.run_sync(lambda conn: inspect(conn).get_table_names()))

        async def columns(connection, table):
            return {item['name'] for item in await connection.run_sync(
                lambda conn: inspect(conn).get_columns(table))}

        # Refuse to destroy any previously populated database, even a test one.
        self.assertEqual(asyncio.run(run(tables)), set(), 'Migration roundtrip requires an EMPTY test database')
        heads = alembic('heads')
        self.assertEqual(heads.count('(head)'), 1)
        self.assertIn('021_drop_chat_tables (head)', heads)

        alembic('upgrade', '020_snapshot_complete')
        before = asyncio.run(run(tables))
        self.assertTrue({'chat_sessions', 'chat_messages'} <= before)
        chat_columns = asyncio.run(run(lambda connection: columns(connection, 'chat_messages')))

        async def seed(connection):
            await connection.execute(text(
                "INSERT INTO chat_sessions(id, owner, title) "
                "VALUES ('00000000-0000-4000-8000-000000000021', 'user:migration', 'legacy')"
            ))
            await connection.execute(text(
                "INSERT INTO agent_sessions(id, owner, title) VALUES ('ses_migration_021', 'user:migration', 'keep')"
            ))
        asyncio.run(run(seed))

        alembic('upgrade', 'head')
        self.assertEqual(asyncio.run(run(tables)), before - {'chat_sessions', 'chat_messages'})

        async def agent_sentinel(connection):
            return await connection.scalar(text(
                "SELECT count(*) FROM agent_sessions WHERE id = 'ses_migration_021'"
            ))
        self.assertEqual(asyncio.run(run(agent_sentinel)), 1)

        alembic('downgrade', '020_snapshot_complete')
        self.assertEqual(asyncio.run(run(tables)), before)
        self.assertEqual(asyncio.run(run(lambda connection: columns(connection, 'chat_messages'))), chat_columns)

        async def legacy_rows(connection):
            return await connection.scalar(text('SELECT count(*) FROM chat_sessions'))
        self.assertEqual(asyncio.run(run(legacy_rows)), 0)

        # Earlier downgrades still find the columns and indexes they remove.
        alembic('downgrade', 'base')
        self.assertEqual(asyncio.run(run(tables)), {'alembic_version'})
        alembic('upgrade', 'head')
        self.assertIn('021_drop_chat_tables (head)', alembic('current'))


if __name__ == '__main__':
    unittest.main()
