"""Backend catalog transport, read-only API and Admin identity regressions."""
import json
import os
import unittest
from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.core.admin_auth import PATH
from app.core.errors import BusinessError
from app.integrations import agent_management as agent
from app.services.agent_entitlements import reconciliation
from app.services.model_metadata import get_model_metadata
from agent_contracts.management import Document


class CatalogTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_encodes_id_and_uses_only_server_role(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(200, json={'schema_version': 1, 'data': {
                'name': 'example', 'resource_digest': 'digest', 'render_safe_markdown': '<script>literal</script>'}})
        original = httpx.AsyncClient
        def client(**kwargs):
            self.assertFalse(kwargs['trust_env'])
            return original(**kwargs, transport=httpx.MockTransport(handle))
        with patch.dict(os.environ, {'AGENT_INTERNAL_URL': 'http://agent.example.invalid', 'AGENT_MANAGEMENT_TOKEN': 'private'}), patch.object(agent.httpx, 'AsyncClient', side_effect=client):
            path = agent.management_path('/skills/{skill_name}/document', {'skill_name': 'example'})
            data = await agent.read(path, Document, {'resource_digest': 'digest'})
        self.assertEqual(data.render_safe_markdown, '<script>literal</script>')
        self.assertEqual(calls[0].method, 'GET')
        self.assertEqual(calls[0].headers['authorization'], 'Bearer private')
        self.assertEqual(calls[0].url.path, '/internal/v2/management/skills/example/document')
        self.assertEqual(calls[0].url.params['resource_digest'], 'digest')
        self.assertEqual(agent.management_path('/models/{model_id:path}', {'model_id': 'fixture/model'}), '/models/fixture/model')
        for key in ['../escape', 'fixture/../escape', 'a\\b', 'a//b']:
            with self.assertRaises(BusinessError):
                agent.management_path('/models/{model_id:path}', {'model_id': key})

    async def test_invalid_upstream_rejected_and_safe_error_retained(self):
        original = httpx.AsyncClient
        for status, payload, expected in [(200, {'schema_version': 1, 'data': {}}, 503),
            (404, {'error': {'reason_code': 'RESOURCE_NOT_FOUND'}}, 404),
            (500, {'password': 'must-not-appear'}, 503)]:
            def client(**kwargs):
                return original(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload)))
            with patch.dict(os.environ, {'AGENT_INTERNAL_URL': 'http://agent.example.invalid', 'AGENT_MANAGEMENT_TOKEN': 'private'}), patch.object(agent.httpx, 'AsyncClient', side_effect=client):
                with self.assertRaises(BusinessError) as raised:
                    await agent.read('/skills/missing', Document, {})
                self.assertEqual(raised.exception.status, expected)
                self.assertNotIn('must-not-appear', raised.exception.message)

    async def test_tunnel_reconciliation_identity_is_accepted_without_weakening_other_callers(self):
        with patch.object(reconciliation, 'admin_lock', new=AsyncMock()), patch.object(reconciliation, 'replay', new=AsyncMock(return_value={'replayed': True})), patch.object(reconciliation, 'request_payload', return_value={}):
            from types import SimpleNamespace
            result = await reconciliation.apply(None, None, 'grant', SimpleNamespace(operation_id='op'), 'ssh-admin:operator', {})
            self.assertEqual(result, {'replayed': True})
            for principal in ['user:operator', 'anonymous', 'operator']:
                with self.assertRaises(Exception) as raised:
                    await reconciliation.apply(None, None, 'grant', SimpleNamespace(operation_id='op'), principal, {})
                self.assertEqual(raised.exception.reason, 'ADMIN_REQUIRED')


class CatalogApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'ADMIN_AUTH_MODE': 'local_password', 'ADMIN_LOCAL_USERNAME': 'admin',
            'ADMIN_LOCAL_PASSWORD': 'test-password', 'ADMIN_SESSION_SECRET': 's' * 40, 'ADMIN_AUTH_LOCAL_ONLY': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app, client=('127.0.0.1', 1234))
        self.addCleanup(self.client.close)

    def login(self):
        self.assertEqual(self.client.post(PATH + '/auth/login', json={'username': 'admin', 'password': 'test-password'}).status_code, 200)

    def test_auth_static_metadata_and_no_refresh_or_write_apis(self):
        self.assertEqual(self.client.get(PATH + '/agent/providers').status_code, 401)
        self.login()
        response = self.client.get(PATH + '/agent/model-metadata/deepseek/deepseek-chat')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertIn('pricing', response.json()['data'])
        self.assertEqual(self.client.post(PATH + '/agent/model-metadata/deepseek/deepseek-chat', json={}).status_code, 405)
        for path in ['config/preview', 'workers', 'tasks', 'overview', 'alerts']:
            self.assertEqual(self.client.get(PATH + '/agent/' + path).status_code, 404)
        paths = {p: methods for p, methods in app.openapi()['paths'].items() if p.startswith(PATH + '/agent/')}
        self.assertEqual(len(paths), 10)
        self.assertTrue(all(set(methods) == {'get'} for methods in paths.values()))

    def test_query_validation_and_document_transport(self):
        self.login()
        self.assertEqual(self.client.get(PATH + '/agent/tools?limit=101').status_code, 422)
        with patch.object(agent, 'read', new=AsyncMock(return_value=Document(name='example', resource_digest='d', render_safe_markdown='# literal')) ) as read:
            response = self.client.get(PATH + '/agent/skills/example/document?resource_digest=d')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['data']['render_safe_markdown'], '# literal')
            self.assertEqual(read.call_args.args[0], '/skills/example/document')
            self.assertEqual(read.call_args.args[2], {'resource_digest': 'd'})

    def test_all_static_metadata_validates_without_network(self):
        from app.services.model_metadata import METADATA_PATH
        entries = json.loads(METADATA_PATH.read_text(encoding='utf-8'))
        self.assertTrue(entries)
        for key in entries:
            self.assertIsNotNone(get_model_metadata(key))
        self.assertEqual(get_model_metadata('missing').pricing, [])
