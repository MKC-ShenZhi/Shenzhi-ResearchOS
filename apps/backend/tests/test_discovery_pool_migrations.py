"""Destructive 017 <-> 018 roundtrip ONLY in an explicitly supplied empty local test database.

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
class DiscoveryPoolMigrationTests(unittest.TestCase):
    def test_single_head_and_017_018_roundtrip(self):
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

        # Refuse to destroy any previously populated database, even a test one.
        self.assertEqual(asyncio.run(run(tables)), set(), 'Migration roundtrip requires an EMPTY test database')
        heads = alembic('heads')
        self.assertEqual(heads.count('(head)'), 1)
        self.assertIn('018_discovery_pool (head)', heads)
        self.assertIn('017_conference_follows -> 018_discovery_pool', alembic('history'))

        alembic('upgrade', '017_conference_follows')
        baseline = asyncio.run(run(tables))
        self.assertNotIn('discovery_pool_papers', baseline)

        async def seed(connection):
            await connection.execute(text(
                "INSERT INTO conference_follows(user_id, conference_id) VALUES ('migration-sentinel', 'ai-aaai')"
            ))
        asyncio.run(run(seed))

        alembic('upgrade', 'head')

        async def check_upgraded(connection):
            pk = await connection.run_sync(lambda conn: inspect(conn).get_pk_constraint('discovery_pool_papers'))
            self.assertEqual(pk['constrained_columns'], ['paper_id'])
            indexes = await connection.run_sync(lambda conn: inspect(conn).get_indexes('discovery_pool_papers'))
            self.assertIn(['year', 'synced_at'], [item['column_names'] for item in indexes])
            # The pool is shared catalogue data, never user-owned.
            fks = await connection.run_sync(lambda conn: inspect(conn).get_foreign_keys('discovery_pool_papers'))
            self.assertEqual(fks, [])
            await connection.execute(text(
                "INSERT INTO discovery_pool_papers(paper_id, title, abstract, authors, year, venue, image_id, "
                "subjects, keywords, synced_at) VALUES ('paper:m', 't', 'a', '[]', 2026, 'V', '/images/m.png', "
                "'[]', '[]', now())"
            ))

        asyncio.run(run(check_upgraded))

        alembic('downgrade', '017_conference_follows')
        self.assertEqual(asyncio.run(run(tables)), baseline)

        async def sentinel(connection):
            return await connection.scalar(text(
                "SELECT count(*) FROM conference_follows WHERE user_id = 'migration-sentinel'"
            ))
        self.assertEqual(asyncio.run(run(sentinel)), 1)

        alembic('upgrade', 'head')
        self.assertIn('018_discovery_pool (head)', alembic('current'))


if __name__ == '__main__':
    unittest.main()
