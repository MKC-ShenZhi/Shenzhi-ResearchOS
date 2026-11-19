"""Opt-in TWO PostgreSQL databases, unique per-test schemas, real row locks.

Both *_A_LINE_TEST_DATABASE_URL must explicitly point at local databases named
shenzhi_a_line_*. No production URLs are inferred. Only our random schemas are
created/dropped. The inherited suite also exercises the HTTP/MockProvider loop.
"""
import asyncio
import importlib.util
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from tests import test_a_line_persistence as suite
from agent_contracts.wire import TaskSubmissionWire
from app.models.agent_entitlements import WindowCounterRow
from agent_contracts.v2 import PermitStart
from app.services.agent_entitlements.service import EntitlementError


@unittest.skipUnless(os.getenv('AGENT_A_LINE_TEST_DATABASE_URL') and os.getenv('BACKEND_A_LINE_TEST_DATABASE_URL'),
                     'two isolated local A-line PostgreSQL databases not selected')
class PostgresALineTests(suite.ALinePersistenceTests):
    async def create_databases(self):
        urls=[os.environ['AGENT_A_LINE_TEST_DATABASE_URL'],os.environ['BACKEND_A_LINE_TEST_DATABASE_URL']]
        for url in urls:
            parsed=urlsplit(url)
            if parsed.hostname not in ('localhost','127.0.0.1') or not parsed.path.startswith('/shenzhi_a_line_'):
                raise RuntimeError('Only explicitly selected local shenzhi_a_line_* databases allowed')
        if urlsplit(urls[0]).path==urlsplit(urls[1]).path:
            raise RuntimeError('Agent and Backend test databases must differ')
        self.schemas=[]
        engines=[]
        root=Path(__file__).resolve().parents[4]
        paths=[root/'apps/agent/migrations/versions/0003_agent_metering.py',
               root/'apps/backend/migrations/versions/027_agent_entitlements.py']
        for index,url in enumerate(urls):
            schema='a_line_'+uuid.uuid4().hex
            engine=create_async_engine(url,connect_args={'server_settings':{'search_path':schema}})
            self.schemas.append((url,schema))
            engines.append(engine)
            async with engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                def migrate(sync):
                    if index==0:
                        legacy=['agent_tasks','agent_runs','agent_run_events','agent_run_controls','agent_outbox']
                        suite.AgentBase.metadata.create_all(sync,tables=[suite.AgentBase.metadata.tables[n] for n in legacy])
                    spec=importlib.util.spec_from_file_location('a_line_migration',paths[index])
                    module=importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await connection.run_sync(migrate)
        self.agent_engine,self.backend_engine=engines
        self.agent=async_sessionmaker(self.agent_engine,expire_on_commit=False)
        self.backend=async_sessionmaker(self.backend_engine,expire_on_commit=False)

    async def asyncTearDown(self):
        await super().asyncTearDown()
        for url,schema in self.schemas:
            if not schema.startswith('a_line_') or len(schema)!=39:
                raise RuntimeError('refuse unsafe schema cleanup')
            engine=create_async_engine(url)
            async with engine.begin() as c:
                await c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await engine.dispose()

    async def test_concurrent_reservation_cannot_overspend(self):
        ready=asyncio.Event()
        async def submit(index):
            await ready.wait()
            request=TaskSubmissionWire(owner_id='user:test',prompt='race',model='test/m1',idempotency_key=str(index))
            try:
                async with self.backend() as db,db.begin():
                    return await self.service.authorize_submission(db,owner_id='user:test',client_key=str(index),
                                                                   request=request.model_dump(mode='json'))
            except EntitlementError as exc:
                return exc
        tasks=[asyncio.create_task(submit(i)) for i in range(3)]
        ready.set()
        results=await asyncio.wait_for(asyncio.gather(*tasks),15)
        self.assertEqual(sum(isinstance(v,EntitlementError) for v in results),1)
        async with self.backend() as db:
            counter=await db.scalar(select(WindowCounterRow))
            self.assertEqual(counter.held,100)

    async def test_concurrent_same_submission_has_one_reservation(self):
        request=TaskSubmissionWire(owner_id='user:test',prompt='race',model='test/m1',idempotency_key='same')
        async def submit():
            async with self.backend() as db,db.begin():
                result=await self.service.authorize_submission(db,owner_id='user:test',client_key='same',
                                                               request=request.model_dump(mode='json'))
                return result[0].submission_id
        results=await asyncio.wait_for(asyncio.gather(submit(),submit(),submit()),15)
        self.assertEqual(len(set(results)),1)
        async with self.backend() as db:
            self.assertEqual((await db.scalar(select(WindowCounterRow))).held,50)

    async def test_revocation_and_start_serialize_on_grant_root(self):
        await self.prepare()
        await self.start_call()
        request=self.permit_request_value.model_copy(update={'call_id':'racing-call','control_attestation_id':'racing-attestation'})
        async with self.backend() as db,db.begin():
            response=await self.service.permit(db,request)
        operation=PermitStart(schema_version=1, start_operation_id='racing-start',execution_id=request.execution_id,
                              control_attestation_id=request.control_attestation_id)
        ready=asyncio.Event()
        async def revoke():
            await ready.wait()
            async with self.backend() as db,db.begin():
                await self.service.revoke(db,self.grant.grant_id,'racing-revoke','test-admin','race-test')
        async def start():
            await ready.wait()
            try:
                async with self.backend() as db,db.begin():
                    return await self.service.start(db,response['permit']['permit_id'],operation)
            except EntitlementError as exc:
                return exc
        tasks=[asyncio.create_task(revoke()),asyncio.create_task(start())]
        ready.set()
        _,result=await asyncio.wait_for(asyncio.gather(*tasks),15)
        if isinstance(result,EntitlementError):
            self.assertEqual(result.reason,'GRANT_INACTIVE')
        else:
            self.assertTrue(result['first_commit'])
        async with self.backend() as db:
            self.assertEqual((await db.scalar(select(WindowCounterRow))).held,50)

    async def test_new_migrations_roundtrip_preserves_agent_legacy_tables(self):
        root=Path(__file__).resolve().parents[4]
        for engine,path in ((self.agent_engine,root/'apps/agent/migrations/versions/0003_agent_metering.py'),
                            (self.backend_engine,root/'apps/backend/migrations/versions/027_agent_entitlements.py')):
            async with engine.begin() as c:
                def roundtrip(sync):
                    spec=importlib.util.spec_from_file_location('a_line_roundtrip',path)
                    module=importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    with Operations.context(MigrationContext.configure(sync)):
                        module.downgrade()
                        module.upgrade()
                await c.run_sync(roundtrip)
        async with self.agent() as db:
            self.assertEqual(await db.scalar(text("SELECT to_regclass('agent_tasks')::text")),'agent_tasks')
