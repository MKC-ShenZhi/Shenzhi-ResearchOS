"""Opt-in destructive roundtrip; only an EMPTY local *_migration_test database."""

import asyncio
import importlib
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import asyncpg
from sqlalchemy.engine import make_url

URL = os.getenv("SHENZHI_CONFERENCE_MIGRATION_TEST_URL", "")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(URL, "SHENZHI_CONFERENCE_MIGRATION_TEST_URL not set")
class ConferenceSyncMigrationTests(unittest.TestCase):
    def test_follow_merge_idempotence_and_snapshot_roundtrip(self):
        parsed = make_url(URL)
        self.assertIn(parsed.host, ("127.0.0.1", "localhost", "::1"))
        self.assertTrue((parsed.database or "").endswith("_migration_test"))

        async def sql(query):
            conn = await asyncpg.connect(URL)
            try:
                return await conn.fetch(query)
            finally:
                await conn.close()

        def execute(query):
            return asyncio.run(sql(query))

        def migrate(*args):
            subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                cwd=ROOT,
                env={**os.environ, "CHAT_DATABASE_URL": URL},
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            execute("SELECT tablename FROM pg_tables WHERE schemaname='public'"), []
        )
        migrate("upgrade", "020_snapshot_complete")
        execute(
            "INSERT INTO conference_follows(user_id,conference_id) VALUES ('a','ds-dcc'),('a','cg-dcc'),('b','se-eusipco')"
        )
        # An environment may already have run the published conference branch.
        migrate("upgrade", "022_conference_snapshots")
        migrate("upgrade", "head")
        self.assertEqual([tuple(row) for row in execute("SELECT version_num FROM alembic_version")], [("023_merge_conference_chat",)])
        rows = execute(
            "SELECT user_id,conference_id FROM conference_follows ORDER BY user_id"
        )
        self.assertEqual(
            [tuple(r) for r in rows], [("a", "cg-dcc"), ("b", "cg-eusipco")]
        )
        # Exercise upgrade SQL again independently of Alembic's version tracking.
        module = importlib.import_module(
            "migrations.versions.021_conference_follow_ids"
        )

        class Operations:
            @staticmethod
            def execute(statement):
                from sqlalchemy.dialects import postgresql

                execute(
                    str(
                        statement.compile(
                            dialect=postgresql.dialect(),
                            compile_kwargs={"literal_binds": True},
                        )
                    )
                )

        with patch.object(module, "op", Operations):
            module.upgrade()
        self.assertEqual(
            [
                tuple(r)
                for r in execute(
                    "SELECT user_id,conference_id FROM conference_follows ORDER BY user_id"
                )
            ],
            [("a", "cg-dcc"), ("b", "cg-eusipco")],
        )
        execute(
            "INSERT INTO conference_snapshots(id,payload,snapshot_id) VALUES (1,'{}','test')"
        )
        with self.assertRaises(asyncpg.CheckViolationError):
            execute("INSERT INTO conference_snapshots(id) VALUES (2)")
        migrate("downgrade", "020_snapshot_complete")
        self.assertEqual(
            execute(
                "SELECT tablename FROM pg_tables WHERE tablename='conference_snapshots'"
            ),
            [],
        )
        migrate("upgrade", "head")
        self.assertEqual(execute("SELECT * FROM conference_snapshots"), [])
