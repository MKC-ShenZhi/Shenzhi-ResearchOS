"""Read-only Admin -> Backend -> Agent contract test over ASGI."""
import asyncio
import os
import shutil
import socket
import subprocess
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from unittest.mock import patch

import httpx
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_app.main import app as agent_app
from tests.test_management import ENV, MODEL, PREFIX, ManagementFixture, deny_writes

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from app.integrations import agent_management as agent
from app.api import admin_console
from app.api.admin_console import router as admin_router
from app.api.agent_management import router as management_router
from app.core.errors import BusinessError
from app.core.responses import fail
from app.models.agent_entitlements import (
    EntitlementPolicyRow, MeteringProfileRow, OwnerEntitlementRow, PlanReleaseRow, UsageProjectionRow,
)
from app.services import agent_management as service

ROOT = '/api/v1/admin-console'
ADMIN = {
    'ADMIN_AUTH_MODE': 'local_password',
    'ADMIN_LOCAL_USERNAME': 'test-admin',
    'ADMIN_LOCAL_PASSWORD': 'test-password',
    'ADMIN_SESSION_SECRET': 'test-only-session-secret-not-for-deployment',
    'AGENT_INTERNAL_URL': 'http://127.0.0.1:18101',
}


class ManagementBridgeTests(ManagementFixture):
    async def asyncSetUp(self):
        names = {'PATH', 'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'HOME'}
        self.node = shutil.which('node')
        self.browser_env = {k: v for k, v in os.environ.items() if k.upper() in names}
        await super().asyncSetUp()
        context = patch.dict(os.environ, ADMIN)
        context.start()
        self.addCleanup(context.stop)
        db_engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.addAsyncCleanup(db_engine.dispose)
        async with db_engine.begin() as connection:
            await connection.run_sync(MeteringProfileRow.__table__.create)
            await connection.run_sync(UsageProjectionRow.__table__.create)
            for table in (EntitlementPolicyRow, OwnerEntitlementRow, PlanReleaseRow):
                await connection.run_sync(table.__table__.create)
            await connection.execute(text('CREATE TABLE "user" (id text, email text, "createdAt" timestamp)'))
            await connection.execute(text("""INSERT INTO "user" VALUES
                ('legacy', 'legacy@example.invalid', '2024-01-01'),
                ('assigned', 'assigned@example.invalid', '2024-01-02'),
                ('new', 'new@example.invalid', '2026-01-01')"""))
        db = async_sessionmaker(db_engine, expire_on_commit=False)
        self.backend_engine = db_engine
        async with db.begin() as session:
            session.add(EntitlementPolicyRow(policy_revision='existing', payload={}, approved=True, test_only=False))
            await session.flush()
            session.add(OwnerEntitlementRow(owner_id='user:assigned', plan_id='basic', policy_revision='existing', enabled=False))
            session.add(MeteringProfileRow(profile_id='attached', owner_id='user:alice', audience='test',
                context='observation_only', provenance='fixture', admission_revision='fixture', request_digest='fixture',
                task_id='task0', enrollment_at=self.now, observation_submission_id='obs:fixture', binding={
                    'schema_version': 1, 'task_id': 'task0', 'metering_profile_id': 'attached',
                    'metering_context': 'observation_only', 'submission_id_source': 'agent_observation',
                    'submission_id': 'obs:fixture', 'bound_at': self.now.isoformat(), 'admission_revision': 'fixture',
                }))
            session.add(UsageProjectionRow(call_id='model-call', task_id='task0', revision=1, start_fact={},
                settlement_status='settled', payload={
                    'owner_id': 'user:alice', 'metering_profile_id': 'attached',
                    'agent_audience': 'test', 'submission_id': 'obs:fixture',
                    'capability_identity': {'kind': 'model'}, 'prompt_tokens': 5, 'completion_tokens': 7,
                    'usage_status': 'measured', 'phase': 'completed',
                }))
        @asynccontextmanager
        async def scope():
            async with db() as session:
                yield session

        legacy = patch.object(admin_console, 'session_scope', scope)
        legacy.start()
        self.addCleanup(legacy.stop)
        database = patch.object(service, 'get_session_factory', return_value=db)
        database.start()
        self.addCleanup(database.stop)
        backend = FastAPI()
        backend.include_router(admin_router)
        backend.include_router(management_router)

        @backend.exception_handler(BusinessError)
        async def errors(_request: Request, exc: BusinessError):
            return fail(exc.code, exc.message, exc.status)

        self.backend_app = backend
        create_client = httpx.AsyncClient
        self.browser = create_client(transport=httpx.ASGITransport(app=backend), base_url='http://127.0.0.1')
        self.addAsyncCleanup(self.browser.aclose)

        def transport(**kwargs):
            return create_client(transport=httpx.ASGITransport(app=agent_app), **kwargs)

        upstream = patch.object(agent.httpx, 'AsyncClient', side_effect=transport)
        upstream.start()
        self.addCleanup(upstream.stop)

    async def test_authenticated_bridge_and_missing_agent_configuration(self):
        path = ROOT + '/agent'
        self.assertEqual((await self.browser.get(path + '/overview')).status_code, 401)
        login = await self.browser.post(ROOT + '/auth/login', json={
            'username': ADMIN['ADMIN_LOCAL_USERNAME'], 'password': ADMIN['ADMIN_LOCAL_PASSWORD'],
        })
        self.assertEqual(login.status_code, 200)
        with deny_writes(self.backend_engine), deny_writes(self.engine):
            for suffix in ('/overview', '/workers', '/providers', '/models/' + MODEL, '/tools', '/skills',
                           '/tasks', '/tasks/task0', '/tasks/task0/runs', '/runs/run0', '/runs/run0/events',
                           '/runs/run0/calls'):
                response = await self.browser.get(path + suffix)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertNotIn(ENV['AGENT_MANAGEMENT_TOKEN'], response.text)
            response = await self.browser.get(path + '/tasks/task0')
            usage = response.json()['data']['backend_usage']
            self.assertEqual(usage['measured_tokens'], 12)
            self.assertIsNone(usage['accounted_tokens'])
            with patch.dict(os.environ, {'AGENT_MANAGEMENT_TOKEN': ''}):
                data = (await self.browser.get(path + '/overview')).json()['data']
                self.assertEqual(data['api']['status'], 'unavailable')
                self.assertEqual(data['backend_db']['status'], 'ok')
        self.assertEqual((await self.browser.get(PREFIX + '/overview')).status_code, 404)
        self.assertEqual((await self.browser.post(path + '/tools')).status_code, 405)

    async def test_existing_plans_and_migration_preview(self):
        await self.browser.post(ROOT + '/auth/login', json={
            'username': ADMIN['ADMIN_LOCAL_USERNAME'], 'password': ADMIN['ADMIN_LOCAL_PASSWORD'],
        })
        with deny_writes(self.backend_engine):
            plans = await self.browser.get(ROOT + '/plans')
            self.assertEqual(plans.status_code, 200, plans.text)
            self.assertEqual([plan['plan_id'] for plan in plans.json()['data']['items']], ['basic', 'pro', 'research'])
            preview = await self.browser.post(ROOT + '/migration/preview', headers={'X-Admin-Request': '1'},
                                              json={'before': '2025-01-01T00:00:00Z', 'limit': 100})
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual([user['id'] for user in preview.json()['data']['items']], ['legacy'])

    @unittest.skipUnless(os.getenv('SHENZHI_TEST_CHROME'), 'requires local Chromium and Admin production build')
    async def test_admin_browser(self):
        # The Agent hop still uses the real ASGI router and query layer. Only the TCP hop is substituted.
        admin = Path(__file__).resolve().parents[2] / 'admin'
        self.backend_app.mount('/', StaticFiles(directory=admin / 'dist', html=True))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
            server = uvicorn.Server(uvicorn.Config(self.backend_app, lifespan='off', log_level='warning'))
            running = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(65):
                    while not server.started:
                        if running.done():
                            running.result()
                            self.fail('isolated Admin server did not start')
                        await asyncio.sleep(0.05)
                    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
                    process = await asyncio.create_subprocess_exec(
                        self.node or 'node', str(admin / 'tests' / 'agent-management-smoke.mjs'),
                        os.environ['SHENZHI_TEST_CHROME'], origin,
                        *(['--phase2'] if getattr(self, 'phase2_browser', False) else []),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=self.browser_env, **options,
                    )
                    try:
                        output, _ = await process.communicate()
                    finally:
                        if process.returncode is None:
                            process.kill()
                            await process.wait()
                    self.assertEqual(process.returncode, 0, output.decode(errors='replace'))
            finally:
                server.should_exit = True
                await running
