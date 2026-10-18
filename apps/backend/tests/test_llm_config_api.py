import json
import os
import unittest
from unittest.mock import patch

import httpx

from app.main import app
from app.integrations.llm.provider import ModelProvider
from app.integrations.llm.resolver import load_registry
from app.services.chat import service as chat
from app.services.chat.repository import repository

ENV = {'DASHSCOPE_API_KEY': 'dash-private', 'DEEPSEEK_API_KEY': 'deep-private',
       'ZHIPU_API_KEY': 'glm-private', 'ZHIPU_MODEL': 'glm-4-plus',
       'AI_ALLOWED_MODELS': 'deepseek-r1', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true'}
OWNER = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'}


class ConfigApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_registry_compatible_fields_filtered_capabilities_no_secrets(self):
        with patch.dict(os.environ, ENV, clear=True):
            registry = load_registry()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
                for purpose in ['chat', 'agent']:
                    response = await client.get(f'/api/v1/{purpose}/config')
                    self.assertEqual(response.status_code, 200, response.text)
                    data = response.json()['data']
                    self.assertEqual(data['models'], registry.public_models(purpose))
                    self.assertEqual(data['default_model'], registry.default_model(purpose).id)
                    for model in data['models']:
                        self.assertTrue({'value', 'label', 'provider', 'enabled'} <= model.keys())
                        if purpose == 'agent':
                            self.assertTrue(model['capabilities']['tool_calling'])
                    for secret in ['dash-private', 'deep-private', 'glm-private', 'api_key', 'base_url']:
                        self.assertNotIn(secret, response.text)
        self.assertNotIn('api_key', json.dumps(app.openapi()).lower())

    async def test_config_no_key_or_unknown_glm_never_claims_agent_availability(self):
        with patch.dict(os.environ, {'ZHIPU_MODEL': 'unknown-version',
                                     'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true'}, clear=True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
                chat_models = (await client.get('/api/v1/chat/config')).json()['data']['models']
                agent_models = (await client.get('/api/v1/agent/config')).json()['data']['models']
                self.assertTrue(all(not model['enabled'] for model in chat_models + agent_models))
                self.assertTrue(any(model['value'] == 'zhipu/unknown-version' for model in chat_models))
                self.assertFalse(any(model['value'] == 'zhipu/unknown-version' for model in agent_models))

    async def test_glm_product_sse_and_client_cannot_override_credentials(self):
        await repository.clear()
        env = {**ENV, 'AI_DEFAULT_MODEL': 'zhipu/glm-4-plus'}
        seen = []
        with patch.dict(os.environ, env, clear=True):
            def handler(request):
                seen.append(request)
                return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"GLM 回答"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
            provider = ModelProvider(transport=httpx.MockTransport(handler))
            with patch.object(chat, 'ModelProvider', return_value=provider):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1', headers=OWNER) as client:
                    created = await client.post('/api/v1/chat/sessions', json={
                        'question': '你好', 'base_url': 'https://attacker.example', 'api_key': 'attacker',
                    })
                    self.assertEqual(created.status_code, 200, created.text)
                    mid = created.json()['data']['message_id']
                    response = await client.get(f'/api/v1/chat/messages/{mid}/stream')
                    self.assertIn('event: delta', response.text)
                    self.assertIn('GLM 回答', response.text)
                    self.assertIn('event: done', response.text)
                    self.assertNotIn('glm-private', response.text)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].url.host, 'open.bigmodel.cn')
        self.assertEqual(seen[0].headers['authorization'], 'Bearer glm-private')
        await repository.close()
