"""Phase 1 management integration with an isolated Agent SQLite database."""
from contextlib import contextmanager
from datetime import timedelta
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_app import management_catalog, management_observations
from agent_app.control.metering import now_utc
from agent_app.execution.metering import controlled_resource_digest
from agent_app.infrastructure.metering_models import CallRow, ExecutionRow, ObservationRow
from agent_app.infrastructure.models import Base, RunEventRow, RunRow, TaskRow
from agent_app.main import app


PREFIX = '/internal/v2/management'
ENV = {
    'AGENT_MANAGEMENT_TOKEN': 'management-test-credential', 'AGENT_WORKER_TOKEN': 'worker-test-credential',
    'AGENT_SERVICE_TOKEN': 'service-test-credential', 'AGENT_BUILD_REVISION': 'test-build',
    'DEEPSEEK_API_KEY': 'test-never-return-model-key', 'AGENT_MODEL_ROUTE_REVISION': 'test-route',
    'AGENT_TOOL_CONFIGURATION_RELEASE': 'test-tool-release',
}
PRIVATE = 'test-private-user-prompt-and-authorization'
PROVIDER = 'deepseek'
MODEL = 'deepseek/deepseek-chat'


@contextmanager
def deny_writes(engine):
    def check(_conn, _cursor, statement, _params, _context, _executemany):
        if not statement.lstrip().upper().startswith('SELECT'):
            raise AssertionError(f'Unexpected statement during management GET: {statement}')

    event.listen(engine.sync_engine, 'before_cursor_execute', check)
    try:
        yield
    finally:
        event.remove(engine.sync_engine, 'before_cursor_execute', check)


class ManagementFixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        chrome = os.getenv('SHENZHI_TEST_CHROME', '')
        fixture_env = dict(ENV, **({'SHENZHI_TEST_CHROME': chrome} if chrome else {}))
        env = patch.dict(os.environ, fixture_env, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)
        self.now = now_utc()
        async with self.db.begin() as db:
            for i in range(3):
                time = self.now - timedelta(minutes=i + 1)
                db.add(TaskRow(task_id=f'task{i}', owner_id='user:alice', status='running', prompt=PRIVATE,
                               request_json={'prompt': PRIVATE, 'mode': 'deep', 'model': MODEL},
                               current_run_id=f'run{i}', created_at=time))
                db.add(RunRow(run_id=f'run{i}', task_id=f'task{i}', attempt=1, worker_id='worker-a',
                              status='running', request_json={'prompt': PRIVATE},
                              report_json={'error_code': PRIVATE, 'error_message': PRIVATE}, created_at=time,
                              started_at=time, lease_token=1, lease_expires_at=self.now + timedelta(minutes=1)))
            await db.flush()
            db.add(ExecutionRow(execution_id='exec0', run_id='run0', task_id='task0', worker_id='worker-a',
                                lease_token=1, sealed=False))
            await db.flush()
            db.add(CallRow(call_id='call0', task_id='task0', execution_id='exec0', state='started',
                           intent={'capability_identity': {'kind': 'tool', 'capability_id': 'tool:web_search'},
                                   'payload': PRIVATE}, start_fact={'capability_id': 'tool:web_search',
                                   'started_at': self.now.isoformat(), 'capability_version': 'test-tool-version'}))
            db.add(CallRow(call_id='historical', task_id='task0', execution_id='exec0', state='completed',
                           intent={'capability_identity': {'kind': 'tool', 'capability_id': 'tool:historical'}},
                           start_fact={'capability_id': 'tool:historical', 'started_at': self.now.isoformat()}))
            db.add(RunEventRow(run_id='run0', task_id='task0', seq=1, turn=0, name='tool_started',
                               data={'prompt': PRIVATE}, occurred_at=self.now))

        async def session():
            async with self.db() as db:
                yield db

        patcher = patch.object(management_observations, 'get_session', session)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1')
        self.addAsyncCleanup(self.client.aclose)

    async def get(self, path, token=ENV['AGENT_MANAGEMENT_TOKEN'], **kwargs):
        response = await self.client.get(PREFIX + path, headers={'Authorization': 'Bearer ' + token}, **kwargs)
        self.assertNotIn(ENV['DEEPSEEK_API_KEY'], response.text)
        self.assertNotIn(ENV['AGENT_MANAGEMENT_TOKEN'], response.text)
        self.assertNotIn(PRIVATE, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        return response

    async def data(self, path, **kwargs):
        response = await self.get(path, **kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['schema_version'], 1)
        return response.json()['data']

class ManagementTests(ManagementFixture):
    async def test_service_credentials_and_get_only(self):
        self.assertEqual((await self.get('/providers', token='')).status_code, 403)
        self.assertEqual((await self.get('/providers', token=ENV['AGENT_WORKER_TOKEN'])).status_code, 403)
        with patch.dict(os.environ, {'AGENT_MANAGEMENT_TOKEN': ENV['AGENT_SERVICE_TOKEN']}):
            self.assertEqual((await self.get('/providers', token=ENV['AGENT_SERVICE_TOKEN'])).status_code, 403)
        self.assertEqual((await self.client.post(PREFIX + '/overview')).status_code, 405)

    async def test_registry_and_dynamic_tools(self):
        with deny_writes(self.engine), patch('agent_app.extensions.skills.SkillStore.tools', side_effect=AssertionError):
            model = await self.data('/models/' + MODEL)
            self.assertEqual(model['provider_id'], PROVIDER)
            self.assertEqual(model['upstream_model_id'], 'deepseek-chat')
            self.assertEqual(model['states']['reachable']['state'], 'unknown')
            self.assertTrue(model['capability_version'])
            provider = await self.data('/providers/' + PROVIDER)
            self.assertTrue(provider['credential_present'])
            self.assertIn(MODEL, provider['model_ids'])
            tools = {row['tool_id']: row for row in (await self.data('/tools', params={'limit': 100}))['items']}
            self.assertEqual(tools['tool:web_search']['registration'], 'base')
            self.assertIn('workspace_or_session', tools['tool:draw_chart']['conditions'])
            self.assertNotIn('tool:run_command', tools)
            self.assertEqual(tools['tool:historical']['registration'], 'observed_only')
            tool = await self.data('/tools/tool:web_search')
            self.assertEqual(tool['latest_call']['run_id'], 'run0')
            self.assertEqual(tool['states']['loaded']['state'], 'unknown')

    async def test_passive_model_evidence_remains_distinct_from_health(self):
        async with self.db.begin() as db:
            db.add(ObservationRow(measurement_id='model-fact', call_id='historical', task_id='task0',
                                  revision=1, sequence=1, submission_key='model-fixture', submission_digest='fixture',
                                  payload={'capability_identity': {'kind': 'model', 'provider_id': PROVIDER,
                                           'registry_model_id': MODEL}, 'capability_version': 'observed-version',
                                           'observed_at': self.now.isoformat(), 'phase': 'completed',
                                           'outcome': 'succeeded', 'usage_status': 'measured'}))
        with deny_writes(self.engine):
            provider = await self.data('/providers/' + PROVIDER)
            model = await self.data('/models/' + MODEL)
        self.assertEqual(provider['latest_observation']['outcome'], 'succeeded')
        self.assertEqual(model['latest_observation']['capability_version'], 'observed-version')
        self.assertEqual(model['states']['healthy']['state'], 'unknown')

    async def test_task_run_filters_cursor_and_select_only(self):
        with deny_writes(self.engine):
            first = await self.data('/tasks', params={'limit': 1})
            self.assertEqual(first['items'][0]['task_id'], 'task0')
            second = await self.data('/tasks', params={'limit': 1, 'cursor': first['next_cursor']})
            self.assertEqual(second['items'][0]['task_id'], 'task1')
            self.assertEqual((await self.data('/tasks', params={'order': 'asc', 'limit': 1}))['items'][0]['task_id'], 'task2')
            bad = await self.get('/tasks', params={'limit': 1, 'status': 'failed', 'cursor': first['next_cursor']})
            self.assertEqual(bad.status_code, 422)
            self.assertEqual((await self.get('/tasks', params={'from_at': '2026-01-01T00:00:00'})).status_code, 422)
            bounds = {'from_at': (self.now - timedelta(seconds=90)).isoformat(), 'to_at': self.now.isoformat()}
            self.assertEqual(len((await self.data('/tasks', params=bounds))['items']), 1)
            self.assertEqual(len((await self.data('/tasks', params={'tool_id': 'web_search'}))['items']), 1)
            self.assertEqual((await self.data('/tasks', params={'model_id': MODEL}))['items'], [])
            self.assertEqual((await self.data('/tasks/task0'))['observed_usage']['status'], 'unknown')
            self.assertEqual(len((await self.data('/tasks/task0/runs'))['items']), 1)
            self.assertEqual((await self.data('/runs/run0'))['execution']['execution_id'], 'exec0')
            self.assertEqual(len((await self.data('/runs/run0/events'))['items']), 1)
            calls = (await self.data('/runs/run0/calls', params={'kind': 'tool'}))['items']
            self.assertEqual({call['run_id'] for call in calls}, {'run0'})
            self.assertIn('call0', {call['call_id'] for call in calls})
            self.assertEqual((await self.data('/workers/worker-a'))['active_executions'], 1)
            self.assertEqual((await self.data('/overview'))['counts']['running_runs'], 3)

    async def test_overview_partial_success(self):
        async def unavailable():
            raise RuntimeError('database unavailable')
            yield

        with patch.object(management_observations, 'get_session', unavailable):
            data = await self.data('/overview')
        self.assertEqual(data['api']['status'], 'ok')
        self.assertEqual(data['api']['build_revision'], 'test-build')
        self.assertEqual(data['agent_db']['status'], 'unavailable')
        self.assertEqual(data['workspace']['writable'], 'unknown')
        self.assertEqual(data['workers']['status'], 'unknown')

    async def test_skill_preview_registered_revision_and_containment(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'sample'
            root.mkdir()
            path = root / 'SKILL.md'
            path.write_text('# Registered resource', encoding='utf-8')
            version = controlled_resource_digest(root)
            skill = SimpleNamespace(root=root, resource_content_digest=version)
            with patch.object(management_catalog, 'default_store', return_value={'sample': skill}):
                response = await self.data('/skills/sample/document', params={'resource_digest': version})
                self.assertEqual(response['render_safe_markdown'], '# Registered resource')
                self.assertEqual((await self.get('/skills/sample/document',
                                 params={'resource_digest': 'wrong'})).status_code, 409)
                self.assertEqual((await self.get('/skills/unregistered/document',
                                 params={'resource_digest': version})).status_code, 404)
                path.write_text('# Changed', encoding='utf-8')
                self.assertEqual((await self.get('/skills/sample/document',
                                 params={'resource_digest': version})).status_code, 409)
                path.write_text('a' * 65_537, encoding='utf-8')
                self.assertEqual((await self.get('/skills/sample/document',
                                 params={'resource_digest': version})).status_code, 422)
