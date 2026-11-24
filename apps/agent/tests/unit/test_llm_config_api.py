import json
import os
import unittest
from unittest.mock import patch

import httpx

from agent_app.main import app
from agent_app.integrations.llm.resolver import load_registry

VERIFIED_AUTODL_UPSTREAMS = ('DeepSeek-V4.1-Flash-1017', 'Qwen3.5-397B-A17B', 'Kimi-K2.5')

ENV = {'DASHSCOPE_API_KEY': 'dash-private', 'DEEPSEEK_API_KEY': 'deep-private',
       'ZHIPU_API_KEY': 'glm-private',
       'AGENT_SERVICE_TOKEN': 'test-token'}


class ConfigApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_registry_compatible_fields_filtered_capabilities_no_secrets(self):
        with patch.dict(os.environ, ENV, clear=True):
            registry = load_registry()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer test-token'}) as client:
                response = await client.get('/internal/v1/config')
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertEqual(data['models'], registry.public_models('agent'))
                self.assertEqual(data['default_model'], registry.public_default('agent'))
                for model in data['models']:
                    self.assertTrue({'value', 'label', 'provider', 'enabled'} <= model.keys())
                    self.assertTrue(model['capabilities']['tool_calling'])
                for secret in ['dash-private', 'deep-private', 'glm-private', 'api_key', 'base_url']:
                    self.assertNotIn(secret, response.text)
        self.assertNotIn('api_key', json.dumps(app.openapi()).lower())

    async def test_config_no_key_never_claims_agent_availability(self):
        with patch.dict(os.environ, {'AGENT_SERVICE_TOKEN': 'test-token'}, clear=True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer test-token'}) as client:
                data = (await client.get('/internal/v1/config')).json()
                self.assertEqual(data['models'], [])
                self.assertIsNone(data['default_model'])

    async def test_autodl_only_catalog_branding_capability_filter_and_no_key_in_response_or_logs(self):
        env = {'AUTODL_API_KEY': 'autodl-private', 'AGENT_SERVICE_TOKEN': 'test-token'}
        with patch.dict(os.environ, env, clear=True):
            registry = load_registry()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer test-token'}) as client:
                response = await client.get('/internal/v1/config')
                self.assertEqual(response.status_code, 200)
                data = response.json()
                expected = [f'autodl/{name}' for name in VERIFIED_AUTODL_UPSTREAMS]
                self.assertEqual([m['value'] for m in data['models']], expected)
                self.assertEqual(data['models'], registry.public_models('agent'))
                self.assertEqual(data['default_model'], f'autodl/{VERIFIED_AUTODL_UPSTREAMS[0]}')
                self.assertTrue(all(m['provider_id'] == 'autodl' for m in data['models']))
                self.assertEqual([m['brand'] for m in data['models'][:3]], ['deepseek', 'platform', 'moonshot'])
                self.assertTrue(all(m['provider'] == m['brand'] for m in data['models']))
                self.assertNotIn('autodl-private', response.text)
                self.assertNotIn('api_key', response.text)
