"""Offline OpenLux configuration and OpenAI-compatible wire acceptance."""
import json
import importlib.util
import io
import os
import unittest
import tempfile
from pathlib import Path
from contextlib import contextmanager, redirect_stdout
from unittest.mock import patch

import httpx

from agent_app.errors import BusinessError
from agent_app.integrations.llm import resolver
from agent_app.integrations.llm.agent_stream import OpenAICompatProvider
from agent_app.integrations.llm.registry import RegistryConfigError
from agent_app.execution.provider import Finish, ModelRequest, ReasoningDelta, TextDelta, ToolCallEvent


# Synthetic IDs are explicitly deployed fixtures, never built-in production models.
ENV = {'OPENLUX_API_KEY': 'openlux-test-secret', 'OPENLUX_BASE_URL': 'https://openlux.example/v1/'}
DATA = {'models': [{'id': f'openlux/{name}', 'provider_id': 'openlux', 'upstream_model': name,
                    'label': name, 'brand': 'openlux', 'capabilities': {'tool_calling': tools}}
                   for name, tools in [('Chat-ID', False), ('Tool-ID', True)]],
        'defaults': {'chat': 'openlux/Chat-ID', 'agent': 'openlux/Tool-ID'}}
BUILTINS = ['deepseek-v4.1-flash', 'qwen3.8-flash', 'glm-5.3-flash', 'kimi-k2.6', 'gemini-3.8-flash']


@contextmanager
def declaration(data=DATA):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'registry.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        yield str(path)


def load(env):
    with declaration() as path, patch.dict(os.environ, {'AI_MODEL_REGISTRY_FILE': path, **env}, clear=True):
        return resolver.load_registry()


class OpenLuxRegistryTests(unittest.TestCase):
    def test_builtin_models_are_fixed_and_credentials_gate_availability(self):
        for env in ({}, {'OPENLUX_API_KEY': ' '}):
            with patch.dict(os.environ, env, clear=True):
                registry = resolver.load_registry()
            self.assertIn('openlux', registry.providers)
            self.assertEqual(registry.providers['openlux'].spec.base_url, 'https://api.openlux.ai/v1')
            self.assertEqual([m.upstream_model for m in registry.models.values() if m.provider_id == 'openlux'], BUILTINS)
            self.assertEqual(registry.public_models('agent'), [])

    def test_exact_ids_capability_opt_in_and_public_projection(self):
        registry = load(ENV)
        self.assertEqual([m.upstream_model for m in registry.models.values() if m.id in ('openlux/Chat-ID', 'openlux/Tool-ID')],
                         ['Chat-ID', 'Tool-ID'])
        resolved = registry.resolve_model('openlux/Tool-ID', 'agent')
        self.assertEqual(resolved.base_url, 'https://openlux.example/v1')
        self.assertEqual(resolved.spec.capabilities.max_output_tokens, 4096)
        self.assertFalse(resolved.spec.capabilities.stream_options)
        self.assertEqual(registry.public_default('agent'), 'openlux/Tool-ID')
        public = [m for m in registry.public_models('agent') if m['value']=='openlux/Tool-ID']
        self.assertEqual([m['value'] for m in public], ['openlux/Tool-ID'])
        self.assertEqual(public[0]['provider'], 'openlux')
        for secret in ('openlux-test-secret', 'base_url', 'api_key'):
            self.assertNotIn(secret, json.dumps(public))
        for model in ('Tool-ID', 'openlux/tool-id'):
            with self.assertRaises(BusinessError):
                registry.resolve_model(model, 'agent')
        with self.assertRaisesRegex(BusinessError, 'Tool Calling'):
            registry.resolve_model('openlux/Chat-ID', 'agent')
        self.assertEqual(load({**ENV, 'OPENLUX_API_KEY': ''}).public_models('agent'), [])

    def test_agent_subset_and_endpoint_validation_do_not_leak_inputs(self):
        for endpoint in ('', 'http://openlux.example/v1', 'https://user:PRIVATE@openlux.example/v1',
                         'https://openlux.example/v1?key=PRIVATE', 'https://openlux.example:invalid/v1'):
            with self.subTest(endpoint=endpoint), self.assertRaises(RegistryConfigError) as error:
                load({**ENV, 'OPENLUX_BASE_URL': endpoint})
            self.assertNotIn('PRIVATE', str(error.exception))

    def test_old_defaults_stay_and_explicit_openlux_defaults_win(self):
        env = {**ENV, 'DASHSCOPE_API_KEY': 'legacy-test-secret'}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolver.load_registry().default_model().id, 'dashscope/qwen-plus')
        registry = load({**env, 'AI_DEFAULT_MODEL': 'openlux/Chat-ID',
                         'AI_AGENT_DEFAULT_MODEL': 'openlux/Tool-ID'})
        self.assertEqual(registry.public_default('chat'), 'openlux/Chat-ID')
        self.assertEqual(registry.public_default('agent'), 'openlux/Tool-ID')

    def test_custom_model_declaration_controls_capabilities(self):
        custom = {'models': [{
            'id': 'openlux/Tool-ID', 'provider_id': 'openlux', 'upstream_model': 'Tool-ID',
            'label': 'Reviewed OpenLux', 'brand': 'openlux',
            'capabilities': {'tool_calling': True, 'stream_options': True, 'reasoning': True,
                             'max_output_tokens': 8192},
        }]}
        with declaration(custom) as path:
            registry = load({**ENV, 'AI_MODEL_REGISTRY_FILE': path})
        caps = registry.resolve_model('openlux/Tool-ID', 'agent').spec.capabilities
        self.assertTrue(caps.stream_options)
        self.assertTrue(caps.reasoning)
        self.assertEqual(caps.max_output_tokens, 8192)
        payload = OpenAICompatProvider(registry=registry)._build_payload(ModelRequest('openlux/Tool-ID', []))
        self.assertEqual(payload['stream_options'], {'include_usage': True})


class OpenLuxProbeTests(unittest.TestCase):
    def test_probe_list_uses_catalog_endpoint_and_does_not_register_models(self):
        source = Path(__file__).resolve().parents[2] / 'scripts/openlux_probe.py'
        spec = importlib.util.spec_from_file_location('openlux_probe_test', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        seen = []

        def handler(request):
            seen.append(request)
            self.assertEqual(str(request.url), 'https://openlux.example/v1/models')
            self.assertEqual(request.headers['authorization'], 'Bearer openlux-test-secret')
            return httpx.Response(200, json={'data': [{'id': 'Catalog-Only-ID'}]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, ENV, clear=True), patch('sys.argv', ['probe', '--list-only']), \
             patch.object(module.httpx, 'Client', return_value=client), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main(), 0)
            self.assertEqual(json.loads(output.getvalue())['T0']['ids'], ['Catalog-Only-ID'])
            self.assertNotIn('openlux-test-secret', output.getvalue())
            self.assertNotIn('openlux/Catalog-Only-ID', resolver.load_registry().models)
            self.assertEqual(resolver.load_registry().public_default('agent'), 'openlux/deepseek-v4.1-flash')
        self.assertEqual(len(seen), 1)


class OpenLuxWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_endpoint_exposes_only_opted_in_models_without_secrets(self):
        from agent_app.main import app

        for tool_enabled, expected in ((True, ['openlux/Tool-ID']), (False, [])):
            data = json.loads(json.dumps(DATA))
            data['models'][1]['capabilities']['tool_calling'] = tool_enabled
            if not tool_enabled:
                data['defaults'].pop('agent')
            with declaration(data) as path, patch.dict(os.environ, {**ENV, 'AI_MODEL_REGISTRY_FILE': path,
                                         'AGENT_SERVICE_TOKEN': 'test-service-token'}, clear=True):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url='http://127.0.0.1',
                                             headers={'Authorization': 'Bearer test-service-token'}) as client:
                    response = await client.get('/internal/v2/config')
                self.assertEqual(response.status_code, 200)
                self.assertEqual([m['value'] for m in response.json()['models'] if m['value'] in ('openlux/Chat-ID', 'openlux/Tool-ID')], expected)
                for secret in ('openlux-test-secret', 'base_url', 'api_key'):
                    self.assertNotIn(secret, response.text)

    async def test_all_builtin_models_use_exact_existing_adapter_route(self):
        with patch.dict(os.environ, ENV, clear=True):
            registry = resolver.load_registry()
        self.assertEqual(registry.public_default('agent'), 'openlux/deepseek-v4.1-flash')
        seen = []
        def handler(request):
            self.assertEqual(str(request.url), 'https://openlux.example/v1/chat/completions')
            self.assertEqual(request.headers['authorization'], 'Bearer openlux-test-secret')
            body = json.loads(request.content)
            seen.append(body['model'])
            self.assertEqual(body['max_tokens'], 4096)
            self.assertEqual(body['stream_options'], {'include_usage': True})
            self.assertNotIn('enable_thinking', body)
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        provider = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
        for upstream in BUILTINS[:-1]:
            result = [e async for e in provider.stream(ModelRequest('openlux/'+upstream, []))]
            self.assertIn(TextDelta('ok'), result)
        self.assertEqual(seen, BUILTINS[:-1])
        with self.assertRaisesRegex(BusinessError, 'Tool Calling'):
            registry.resolve_model('openlux/gemini-3.8-flash', 'agent')
        self.assertEqual(len(registry.public_models('chat')), 5)

    async def test_missing_credentials_or_tools_rejected_before_transport(self):
        for env, model, message in [({**ENV, 'OPENLUX_API_KEY': ''}, 'openlux/Tool-ID', '凭据'),
                                     (ENV, 'openlux/Chat-ID', 'Tool Calling'),
                                     (ENV, 'openlux/undeclared', '未注册')]:
            def forbidden(request):
                self.fail('Rejected model reached transport')
            provider = OpenAICompatProvider(registry=load(env), transport=httpx.MockTransport(forbidden))
            with self.assertRaisesRegex(BusinessError, message):
                _ = [e async for e in provider.stream(ModelRequest(model, []))]

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
