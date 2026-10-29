"""Destructive 014 <-> 015 roundtrip ONLY in an explicitly supplied empty local test database.

Run with SHENZHI_MIGRATION_TEST_URL pointing at a disposable *_migration_test
PostgreSQL database. Never uses CHAT_DATABASE_URL implicitly. Use a different
empty database than test_interaction_migrations, which leaves its database at 014.
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
RECOMMENDATION_TABLES = {'behavior_events', 'user_interest_profiles', 'recommendation_snapshots'}


@unittest.skipUnless(MIGRATION_URL, 'SHENZHI_MIGRATION_TEST_URL not set (disposable local database required)')
class RecommendationMigrationTests(unittest.TestCase):
    def test_single_head_roundtrip_keeps_interaction_data(self):
        url = make_url(MIGRATION_URL)
        self.assertIn(url.host, ('127.0.0.1', 'localhost', '::1'))
        self.assertTrue((url.database or '').endswith('_migration_test'))
        async_url = url.set(drivername='postgresql+asyncpg')

        async def run(check):
            engine = create_async_engine(async_url)
            try:
                async with engine.begin() as connection:
                    return await check(connection)
            finally:
                await engine.dispose()

        def tables():
            return set(asyncio.run(run(lambda connection: connection.run_sync(
                lambda conn: inspect(conn).get_table_names(),
            ))))

        # Refuse to destroy any previously populated database, even a test one.
        self.assertEqual(tables(), set(), 'Migration roundtrip requires an EMPTY test database')

        def alembic(*args):
            result = subprocess.run(
                [sys.executable, '-m', 'alembic', *args], cwd=ROOT,
                env={**os.environ, 'CHAT_DATABASE_URL': MIGRATION_URL},
                text=True, capture_output=True, check=True,
            )
            return result.stdout + result.stderr

        # 016_request_idempotency now builds on 015 and owns the single-head
        # check; this test keeps the 014-015 contract.
        self.assertIn('014_platform_snapshots -> 015_recommendation_foundation', alembic('history'))

        alembic('upgrade', '014_platform_snapshots')
        baseline = tables()
        self.assertTrue(RECOMMENDATION_TABLES.isdisjoint(baseline))

        async def seed(connection):
            await connection.execute(text(
                "INSERT INTO paper_likes(user_id, paper_id) VALUES ('migration-sentinel', 'paper:sentinel')"
            ))
        asyncio.run(run(seed))

        alembic('upgrade', '015_recommendation_foundation')
        self.assertIn('015_recommendation_foundation', alembic('current'))
        self.assertEqual(tables(), baseline | RECOMMENDATION_TABLES)

        async def check_schema(connection):
            def describe(conn):
                inspector = inspect(conn)
                return {
                    table: {
                        'pk': inspector.get_pk_constraint(table)['constrained_columns'],
                        'indexes': {item['name']: item['column_names'] for item in inspector.get_indexes(table)},
                        'fks': inspector.get_foreign_keys(table),
                    }
                    for table in RECOMMENDATION_TABLES
                }
            return await connection.run_sync(describe)

        schema = asyncio.run(run(check_schema))
        self.assertEqual(schema['behavior_events']['pk'], ['event_id'])
        self.assertEqual(schema['user_interest_profiles']['pk'], ['user_id'])
        self.assertEqual(schema['recommendation_snapshots']['pk'], ['request_id'])
        self.assertEqual(schema['behavior_events']['indexes']['idx_behavior_events_user_entity'],
                         ['user_id', 'entity_type', 'entity_id'])
        self.assertEqual(schema['behavior_events']['indexes']['idx_behavior_events_received'], ['received_at'])
        self.assertIn('idx_behavior_events_user_time', schema['behavior_events']['indexes'])
        self.assertEqual(schema['recommendation_snapshots']['indexes']['idx_recommendation_snapshots_user_expiry'],
                         ['user_id', 'expires_at'])
        # Owners are Better Auth ids in a separate database, so these facts
        # carry no FK; account deletion removes them explicitly.
        self.assertTrue(all(not item['fks'] for item in schema.values()))

        async def duplicate_event_is_rejected(connection):
            statement = text(
                "INSERT INTO behavior_events(event_id, user_id, event_type, entity_type, entity_id, source) "
                "VALUES ('00000000-0000-4000-8000-000000000001', 'u', 'paper_click', 'paper', 'p', 'discovery') "
                "ON CONFLICT (event_id) DO NOTHING"
            )
            first = (await connection.execute(statement)).rowcount
            second = (await connection.execute(statement)).rowcount
            return first, second
        self.assertEqual(asyncio.run(run(duplicate_event_is_rejected)), (1, 0))

        alembic('downgrade', '014_platform_snapshots')
        self.assertEqual(tables(), baseline)

        async def sentinel(connection):
            return await connection.scalar(text(
                "SELECT count(*) FROM paper_likes WHERE user_id = 'migration-sentinel'"
            ))
        self.assertEqual(asyncio.run(run(sentinel)), 1)

        alembic('upgrade', '015_recommendation_foundation')
        self.assertIn('015_recommendation_foundation', alembic('current'))
        self.assertEqual(asyncio.run(run(sentinel)), 1)
