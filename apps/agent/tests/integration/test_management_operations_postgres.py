"""Opt-in Phase 4 operations on a disposable PostgreSQL schema."""
import os
import unittest
import asyncio
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests import test_management_operations as suite
from tests import test_management as fixture


@unittest.skipUnless(os.getenv('PHASE4_TEST_DATABASE_URL'), 'isolated Phase 4 PostgreSQL not selected')
class PostgresManagementOperationsTests(suite.ManagementOperationsTests):
    async def test_drain_waits_for_inflight_claim_transaction_lock(self):
        from agent_contracts.management_operations import ActorManagementAction
        from agent_app import management_operations as ops
        body = ActorManagementAction(operation_id=uuid4(), kind='worker', target_id='worker-a',
            action='drain', reason='race', actor='test-admin')
        async with self.db() as db:
            await ops.worker_lock(db, 'worker-a')
            operation = asyncio.create_task(ops.act(body))
            try:
                await asyncio.sleep(0.1)
                self.assertFalse(operation.done())
                await db.commit()
                result = await asyncio.wait_for(operation, 5)
                self.assertEqual(result['state'], 'accepted')
            finally:
                await db.rollback()
                if not operation.done():
                    operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)

    async def asyncSetUp(self):
        url = os.environ['PHASE4_TEST_DATABASE_URL']
        parsed = urlsplit(url)
        if parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path != '/phase3accept':
            raise RuntimeError('Only the isolated Phase 4 loopback database is allowed')
        schema = 'phase4_' + uuid4().hex
        engine = create_async_engine(url)
        async with engine.begin() as db:
            await db.execute(text(f'CREATE SCHEMA {schema}'))
        await engine.dispose()

        async def cleanup():
            engine = create_async_engine(url)
            async with engine.begin() as db:
                await db.execute(text(f'DROP SCHEMA {schema} CASCADE'))
            await engine.dispose()
        self.addAsyncCleanup(cleanup)
        create = lambda *_args, **_kwargs: create_async_engine(url,
            connect_args={'server_settings': {'search_path': schema}}, hide_parameters=True)
        with patch.object(fixture, 'create_async_engine', side_effect=create):
            await super().asyncSetUp()
