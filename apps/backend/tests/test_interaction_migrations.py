"""Destructive roundtrip ONLY in an explicitly supplied empty local test database.

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
class InteractionMigrationTests(unittest.TestCase):
    def test_upgrade_downgrade_preserves_dev_tables_and_constraints(self):
        url = make_url(MIGRATION_URL)
        self.assertIn(url.host, ('127.0.0.1', 'localhost', '::1'))
        self.assertTrue((url.database or '').endswith('_migration_test'))
        async_url = url.set(drivername='postgresql+asyncpg')

        async def inspect_db():
            engine = create_async_engine(async_url)
            try:
                async with engine.connect() as connection:
                    tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                    return tables
            finally:
                await engine.dispose()

        # Refuse to destroy any previously populated database, even a test one.
        self.assertEqual(asyncio.run(inspect_db()), [], 'Migration roundtrip requires an EMPTY test database')

        def alembic(*args):
            result = subprocess.run(
                [sys.executable, '-m', 'alembic', *args], cwd=ROOT,
                env={**os.environ, 'CHAT_DATABASE_URL': MIGRATION_URL},
                text=True, capture_output=True, check=True,
            )
            return result.stdout + result.stderr

        # Later features may stack on 014; this roundtrip covers 011 -> 014 only.
        self.assertEqual(alembic('heads').count('(head)'), 1)
        alembic('upgrade', '011_agent_uploads')
        baseline = set(asyncio.run(inspect_db()))
        self.assertIn('agent_uploads', baseline)
        self.assertNotIn('paper_likes', baseline)
        alembic('upgrade', '014_platform_snapshots')
        self.assertIn('014_platform_snapshots', alembic('current'))

        async def check_schema():
            engine = create_async_engine(async_url)
            try:
                async with engine.begin() as connection:
                    for table, key in [('paper_likes', 'paper_id'), ('topic_follows', 'topic_id')]:
                        pk = await connection.run_sync(lambda conn: inspect(conn).get_pk_constraint(table))
                        self.assertEqual(set(pk['constrained_columns']), {'user_id', key})
                        indexes = await connection.run_sync(lambda conn: inspect(conn).get_indexes(table))
                        self.assertTrue(any(item['column_names'] == [key] for item in indexes))
                    for table in ['paper_stats_daily', 'topic_stats_daily']:
                        fks = await connection.run_sync(lambda conn: inspect(conn).get_foreign_keys(table))
                        self.assertEqual(fks[0]['referred_table'], 'stats_snapshot_runs')
                        self.assertEqual(fks[0]['options']['ondelete'], 'CASCADE')
                        checks = await connection.run_sync(lambda conn: inspect(conn).get_check_constraints(table))
                        self.assertTrue(checks)
                    await connection.execute(text("INSERT INTO collection_user_states(user_id) VALUES ('migration-sentinel')"))
            finally:
                await engine.dispose()

        asyncio.run(check_schema())
        # Stepwise rollback removes only the relevant extension at each revision.
        for revision, absent in [
            ('013_paper_likes', {'stats_snapshot_runs', 'paper_stats_daily', 'topic_stats_daily'}),
            ('012_topic_follows', {'paper_likes'}),
            ('011_agent_uploads', {'topic_follows'}),
        ]:
            alembic('downgrade', revision)
            self.assertTrue(absent.isdisjoint(asyncio.run(inspect_db())))
        self.assertEqual(set(asyncio.run(inspect_db())), baseline)
        alembic('upgrade', '014_platform_snapshots')

        async def verify_sentinel():
            engine = create_async_engine(async_url)
            try:
                async with engine.connect() as connection:
                    self.assertEqual(await connection.scalar(text(
                        "SELECT count(*) FROM collection_user_states WHERE user_id = 'migration-sentinel'"
                    )), 1)
            finally:
                await engine.dispose()

        asyncio.run(verify_sentinel())
        self.assertIn('014_platform_snapshots', alembic('current'))
