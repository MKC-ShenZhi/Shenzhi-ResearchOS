"""Formal-plan PostgreSQL row-lock and migration checks in opt-in isolated DBs."""
import os
import asyncio
import unittest
from pathlib import Path
import importlib.util
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from alembic.migration import MigrationContext
from alembic.operations import Operations
from tests import test_formal_plans as formal
from tests.integration import test_a_line_postgres as pg
from app.models.agent_entitlements import WindowCounterRow


@unittest.skipUnless(os.getenv('AGENT_A_LINE_TEST_DATABASE_URL') and os.getenv('BACKEND_A_LINE_TEST_DATABASE_URL'),
                     'two isolated local PostgreSQL databases not selected')
class FormalPostgresTests(formal.FormalPlanTests):
    async def create_databases(self):
        await pg.PostgresALineTests.create_databases(self)
        path=Path(__file__).resolve().parents[4]/'apps/backend/migrations/versions/028_formal_plans.py'
        spec=importlib.util.spec_from_file_location('formal_migration',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        async with self.backend_engine.begin() as connection:
            def migrate(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.upgrade();module.downgrade();module.upgrade()
            await connection.run_sync(migrate)

    async def asyncTearDown(self):
        await self.agent_engine.dispose();await self.backend_engine.dispose()
        for url,schema in self.schemas:
            if not schema.startswith('a_line_') or len(schema)!=39:raise RuntimeError('unsafe schema cleanup')
            engine=create_async_engine(url)
            async with engine.begin() as c:await c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await engine.dispose()

    async def test_formal_concurrent_permits_share_one_daily_budget(self):
        await self.formal_setup()
        await self.prepare()
        # Two tasks owned by the same user, both with a valid signed receipt.
        await self.start_call('seed-request')
        request=self.permit_request_value
        # Bind a distinct second task; its permit competes on the same owner row.
        await self.submit(key='second-parallel-task');await self.bind();await self.claim(worker='second-worker')
        from agent_contracts.execution_v2 import CallIntent
        from agent_contracts.canonical import digest
        body=CallIntent(**self.worker.model_dump(),call_id='second-task-call',logical_call_id='second-task-call',
            capability_identity=self.identity,invocation_mode='internal',purpose='main',parent_call_id=None,
            activation_id=None,logical_attempt=1,transport_attempt=1,provider_id='test',request_digest=digest('second'),
            input_bound_evidence_ref=None,output_bound_evidence_ref=None,risk_profile='test-risk-explicitly-approved',model_budget=self.model_budget)
        async with self.agent() as db,db.begin():await self.control.intent(db,self.run.run_id,body)
        async with self.agent() as db:second_request=await self.control.permit_request(db,body.call_id)
        async with self.backend() as db,db.begin():
            counter=await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id=='daily-tokens'))
            counter.used=199974 # one 20-unit call already held; exactly one more fits
        async def authorize(index):
            original=request if index==1 else second_request
            body=original.model_copy(update={'call_id':'concurrent-'+str(index), 'control_attestation_id':'attestation-'+str(index)})
            async with self.backend() as db,db.begin():return await self.service.permit(db,body)
        results=await asyncio.wait_for(asyncio.gather(authorize(1),authorize(2)),15)
        self.assertEqual(sum(r['decision']=='authorized' for r in results),1)
        async with self.backend() as db:
            counter=await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id=='daily-tokens'))
            self.assertEqual((counter.used,counter.held),(199974,26))
