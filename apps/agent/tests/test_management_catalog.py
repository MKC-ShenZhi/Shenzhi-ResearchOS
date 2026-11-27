"""Read-only catalog boundaries, using real factories with no external calls."""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent_app.main import app
from agent_app import management_catalog as catalog
from agent_app.integrations.llm.registry import Catalog, ModelRegistry


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'AGENT_MANAGEMENT_TOKEN': 'catalog-secret',
            'AGENT_GATEWAY_TOKEN': 'gateway-secret', 'AGENT_WORKER_TOKEN': 'worker-secret'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer catalog-secret'}

    def get(self, path, **kwargs):
        return self.client.get('/internal/v2/management' + path, headers=self.headers, **kwargs)

    def test_auth_isolation_and_existing_gateway(self):
        self.assertEqual(self.client.get('/internal/v2/management/tools').status_code, 403)
        self.assertEqual(self.client.get('/internal/v2/management/tools',
            headers={'Authorization': 'Bearer worker-secret'}).status_code, 403)
        with patch.dict(os.environ, {'AGENT_MANAGEMENT_TOKEN': 'worker-secret'}):
            self.assertEqual(self.get('/tools').status_code, 403)
        self.assertEqual(self.client.get('/internal/v2/protocol-capabilities', headers=self.headers).status_code, 403)
        self.assertEqual(self.client.get('/internal/v2/protocol-capabilities',
            headers={'Authorization': 'Bearer gateway-secret'}).status_code, 200)

    def test_tools_are_real_schemas_including_conditional_file_tools(self):
        response = self.get('/tools?limit=100')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        tools = {item['tool_id']: item for item in response.json()['data']['items']}
        for name in ['web_search', 'read_paper', 'fetch_url', 'read_file', 'write_file', 'edit_file']:
            self.assertIn('tool:' + name, tools)
            self.assertIsInstance(tools['tool:' + name]['parameters_schema'], dict)
        self.assertNotIn('tool:run_command', tools)
        self.assertEqual(tools['tool:read_file']['conditions'], ['workspace_or_session'])
        self.assertEqual(self.get('/tools/tool:read_file').status_code, 200)
        self.assertEqual(self.get('/tools/tool:missing').status_code, 404)

    def test_pagination_and_filter_bound_cursor(self):
        first = self.get('/tools?limit=2').json()['data']
        self.assertEqual(len(first['items']), 2)
        self.assertTrue(first['next_cursor'])
        second = self.get('/tools', params={'limit': 2, 'cursor': first['next_cursor']})
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first['items'], second.json()['data']['items'])
        for params in [{'cursor': 'bad'}, {'limit': 2, 'search': 'file', 'cursor': first['next_cursor']}, {'limit': 101}]:
            self.assertEqual(self.get('/tools', params=params).status_code, 422)
        result = self.get('/tools?search=file&order=desc').json()['data']['items']
        self.assertTrue(result)
        ids = [item['tool_id'] for item in result]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertTrue(all('file' in key for key in ids))

    def test_registry_projection_never_exposes_credentials(self):
        registry = ModelRegistry(Catalog.model_validate({
            'providers': [{'id': 'fixture', 'base_url': 'https://provider.example.invalid/v1', 'api_key_env': 'FIXTURE_KEY'}],
            'models': [{'id': 'fixture/model', 'provider_id': 'fixture', 'upstream_model': 'model', 'label': 'Fixture'}],
        }), {'FIXTURE_KEY': 'must-never-appear'})
        with patch.object(catalog, 'load_registry', return_value=registry):
            response = self.get('/providers/fixture')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn('must-never-appear', response.text)
            self.assertNotIn('FIXTURE_KEY', response.text)
            item = response.json()['data']
            self.assertTrue(item['credential_present'])
            self.assertEqual(item['base_url'], 'https://provider.example.invalid')
            model = self.get('/models/fixture/model')
            self.assertEqual(model.status_code, 200, model.text)
            self.assertEqual(model.json()['data']['upstream_model_id'], 'model')

    def test_skill_document_digest_and_literal_text(self):
        entries = self.get('/skills').json()['data']['items']
        self.assertTrue(entries)
        skill = entries[0]
        self.assertEqual(skill['integrity'], 'yes')
        detail = self.get('/skills/' + skill['name'])
        self.assertEqual(detail.status_code, 200)
        doc = self.get('/skills/' + skill['name'] + '/document', params={'resource_digest': skill['resource_digest']})
        self.assertEqual(doc.status_code, 200, doc.text)
        self.assertIn('render_safe_markdown', doc.json()['data'])
        self.assertEqual(self.get('/skills/' + skill['name'] + '/document',
            params={'resource_digest': 'stale'}).status_code, 409)
        self.assertEqual(self.get('/skills/missing').status_code, 404)

    def test_no_new_management_mutations_or_runtime_endpoints(self):
        schema = app.openapi()['paths']
        management = {path: methods for path, methods in schema.items() if '/management' in path}
        self.assertEqual(len(management), 9)
        self.assertTrue(all(set(methods) == {'get'} for methods in management.values()))
        for path in ['/tasks', '/workers', '/overview', '/config', '/alerts']:
            self.assertEqual(self.get(path).status_code, 404)
        self.assertEqual(self.client.post('/internal/v2/management/providers', headers=self.headers, json={}).status_code, 405)
        self.assertNotIn('/internal/v1/tasks', schema)
