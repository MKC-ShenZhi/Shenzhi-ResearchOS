"""Offline OpenLux configuration and OpenAI-compatible wire acceptance."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

from agent_app.errors import BusinessError
from agent_app.integrations.llm import resolver
from agent_app.integrations.llm.agent_stream import OpenAICompatProvider
from agent_app.integrations.llm.registry import Catalog, RegistryConfigError
from agent_app.execution.provider import Finish, ModelRequest, ReasoningDelta, TextDelta, ToolCallEvent


ENV = {'OPENLUX_API_KEY': 'openlux-test-secret', 'OPENLUX_BASE_URL': 'https://openlux.example/v1/',
       'OPENLUX_MODELS': 'Chat-ID,Tool-ID', 'OPENLUX_AGENT_MODELS': 'Tool-ID'}


def load(env):
    with patch.dict(os.environ, env, clear=True):
        return resolver.load_registry()


class OpenLuxRegistryTests(unittest.TestCase):
    def test_registration_requires_key_and_explicit_models(self):
        for env in ({}, {**ENV, 'OPENLUX_API_KEY': ' '}, {**ENV, 'OPENLUX_MODELS': ' , '}):
            registry = load(env)
            self.assertNotIn('openlux', registry.providers)
            self.assertFalse(any(m.provider_id == 'openlux' for m in registry.models.values()))

    def test_exact_ids_capability_opt_in_and_public_projection(self):
        registry = load({**ENV, 'OPENLUX_MODELS': ' Chat-ID,Tool-ID, Chat-ID, ,',
                         'OPENLUX_AGENT_MODELS': ' Tool-ID, Tool-ID, '})
        self.assertEqual([m.upstream_model for m in registry.models.values() if m.provider_id == 'openlux'],
                         ['Chat-ID', 'Tool-ID'])
        resolved = registry.resolve_model('openlux/Tool-ID', 'agent')
        self.assertEqual(resolved.base_url, 'https://openlux.example/v1')
        self.assertEqual(resolved.spec.capabilities.max_output_tokens, 4096)
        self.assertFalse(resolved.spec.capabilities.stream_options)
        self.assertEqual(registry.public_default('agent'), 'openlux/Tool-ID')
        public = registry.public_models('agent')
        self.assertEqual([m['value'] for m in public], ['openlux/Tool-ID'])
        self.assertEqual(public[0]['provider'], 'openlux')
        for secret in ('openlux-test-secret', 'base_url', 'api_key'):
            self.assertNotIn(secret, json.dumps(public))
        for model in ('Tool-ID', 'openlux/tool-id'):
            with self.assertRaises(BusinessError):
                registry.resolve_model(model, 'agent')
        with self.assertRaisesRegex(BusinessError, 'Tool Calling'):
            registry.resolve_model('openlux/Chat-ID', 'agent')
        self.assertEqual(load({**ENV, 'OPENLUX_AGENT_MODELS': ''}).public_models('agent'), [])

    def test_agent_subset_and_endpoint_validation_do_not_leak_inputs(self):
        with self.assertRaises(RegistryConfigError):
            load({**ENV, 'OPENLUX_AGENT_MODELS': 'unknown'})
        for endpoint in ('', 'http://openlux.example/v1', 'https://user:PRIVATE@openlux.example/v1',
                         'https://openlux.example/v1?key=PRIVATE', 'https://openlux.example:invalid/v1'):
            with self.subTest(endpoint=endpoint), self.assertRaises(RegistryConfigError) as error:
                load({**ENV, 'OPENLUX_BASE_URL': endpoint})
            self.assertNotIn('PRIVATE', str(error.exception))

    def test_old_defaults_stay_and_explicit_openlux_defaults_win(self):
        env = {**ENV, 'DASHSCOPE_API_KEY': 'legacy-test-secret'}
        self.assertEqual(load(env).default_model().id, 'dashscope/qwen-plus')
        registry = load({**env, 'AI_DEFAULT_MODEL': 'openlux/Chat-ID',
                         'AI_AGENT_DEFAULT_MODEL': 'openlux/Tool-ID'})
        self.assertEqual(registry.public_default('chat'), 'openlux/Chat-ID')
        self.assertEqual(registry.public_default('agent'), 'openlux/Tool-ID')

    def test_custom_model_declaration_replaces_generated_capabilities(self):
        custom = Catalog.model_validate({'models': [{
            'id': 'openlux/Tool-ID', 'provider_id': 'openlux', 'upstream_model': 'Tool-ID',
            'label': 'Reviewed OpenLux', 'brand': 'openlux',
            'capabilities': {'tool_calling': True, 'stream_options': True, 'reasoning': True,
                             'max_output_tokens': 8192},
        }]})
        original = resolver._read_catalog
        with patch.object(resolver, '_read_catalog', side_effect=lambda path:
                          custom if str(path) == 'in-memory.json' else original(path)):
            registry = load({**ENV, 'AI_MODEL_REGISTRY_FILE': 'in-memory.json'})
        caps = registry.resolve_model('openlux/Tool-ID', 'agent').spec.capabilities
        self.assertTrue(caps.stream_options)
        self.assertTrue(caps.reasoning)
        self.assertEqual(caps.max_output_tokens, 8192)
        payload = OpenAICompatProvider(registry=registry)._build_payload(ModelRequest('openlux/Tool-ID', []))
        self.assertEqual(payload['stream_options'], {'include_usage': True})


class OpenLuxWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_endpoint_exposes_only_opted_in_models_without_secrets(self):
        from agent_app.main import app

        for agent_models, expected in (('Tool-ID', ['openlux/Tool-ID']), ('', [])):
            with patch.dict(os.environ, {**ENV, 'OPENLUX_AGENT_MODELS': agent_models,
                                         'AGENT_SERVICE_TOKEN': 'test-service-token'}, clear=True):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url='http://127.0.0.1',
                                             headers={'Authorization': 'Bearer test-service-token'}) as client:
                    response = await client.get('/internal/v1/config')
                self.assertEqual(response.status_code, 200)
                self.assertEqual([m['value'] for m in response.json()['models']], expected)
                for secret in ('openlux-test-secret', 'base_url', 'api_key'):
                    self.assertNotIn(secret, response.text)

    async def test_existing_adapter_streams_reasoning_tools_and_usage_on_two_rounds(self):
        registry = load(ENV)
        requests = []

        def frame(data):
            return 'data: ' + json.dumps(data) + '\n\n'

        def handler(request):
            self.assertEqual(str(request.url), 'https://openlux.example/v1/chat/completions')
            self.assertEqual(request.headers['authorization'], 'Bearer openlux-test-secret')
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(body['model'], 'Tool-ID')
            self.assertTrue(body['stream'])
            self.assertEqual(body['max_tokens'], 4096)
            self.assertNotIn('enable_thinking', body)
            self.assertNotIn('stream_options', body)
            if len(requests) == 1:
                content = frame({'choices': [{'delta': {'reasoning_content': 'thinking', 'tool_calls': [
                    {'index': 0, 'id': 'call-1', 'function': {'name': 'echo', 'arguments': '{"x":'}}]},
                    'finish_reason': None}]})
                content += frame({'choices': [{'delta': {'tool_calls': [
                    {'index': 0, 'function': {'arguments': '1}'}}]}, 'finish_reason': 'tool_calls'}]})
            else:
                self.assertEqual(body['messages'][-1]['tool_call_id'], 'call-1')
                content = frame({'choices': [{'delta': {'content': 'done'}, 'finish_reason': 'stop'}]})
            content += frame({'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 3}})
            return httpx.Response(200, text=content + 'data: [DONE]\n\n')

        provider = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
        messages = [{'role': 'user', 'content': 'echo'}]
        tools = [{'type': 'function', 'function': {'name': 'echo', 'parameters': {'type': 'object'}}}]
        first = [event async for event in provider.stream(ModelRequest('openlux/Tool-ID', messages, tools=tools))]
        self.assertIn(ReasoningDelta('thinking'), first)
        call = next(event.call for event in first if isinstance(event, ToolCallEvent))
        self.assertEqual(call.arguments, {'x': 1})
        messages += [{'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': call.call_id, 'type': 'function', 'function': {'name': call.name, 'arguments': '{"x":1}'}}]},
            {'role': 'tool', 'tool_call_id': call.call_id, 'content': '1'}]
        second = [event async for event in provider.stream(ModelRequest('openlux/Tool-ID', messages, tools=tools))]
        self.assertIn(TextDelta('done'), second)
        for events in (first, second):
            usage = next(event.usage for event in events if isinstance(event, Finish))
            self.assertEqual((usage.prompt_tokens, usage.completion_tokens), (10, 3))
        self.assertEqual(len(requests), 2)


if __name__ == '__main__':
    unittest.main()
