"""Offline acceptance: actual wire routing through the Agent adapter."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from app.core.errors import BusinessError
from app.integrations.llm.resolver import AUTODL_DEFAULT_MODELS, load_registry
from app.services.agent.provider import OpenAICompatProvider, ModelRequest, TextDelta, ToolCallEvent
from app.services.agent.runtime import AgentRuntime

ENV = {'DASHSCOPE_API_KEY': 'dash-secret', 'DEEPSEEK_API_KEY': 'deep-secret',
       'ZHIPU_API_KEY': 'glm-secret', 'ZHIPU_MODEL': 'glm-4-plus'}


def sse(delta, finish='stop'):
    return 'data: ' + json.dumps({'choices': [{'delta': delta, 'finish_reason': finish}]}) + '\n\ndata: [DONE]\n\n'


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_autodl_adapter_preserves_exact_wire_routing(self):
        with patch.dict(os.environ, {**ENV, 'AUTODL_API_KEY': 'autodl-private'}, clear=True):
            registry = load_registry()
        seen = []

        def handler(request):
            self.assertEqual(request.url.host, 'www.autodl.art')
            self.assertEqual(request.url.path, '/api/v1/chat/completions')
            self.assertEqual(request.headers['authorization'], 'Bearer autodl-private')
            seen.append(json.loads(request.content))
            return httpx.Response(200, text=sse({'content': '正文', 'reasoning_content': '思考'}))

        agent = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
        # The Agent adapter logs nothing at INFO, so the key cannot reach logs.
        with self.assertNoLogs('app', level='INFO'):
            for upstream in AUTODL_DEFAULT_MODELS:
                model = f'autodl/{upstream}'
                self.assertIn(TextDelta('正文'), [e async for e in agent.stream(ModelRequest(model, []))])
                self.assertEqual(seen[-1]['model'], upstream)
                self.assertEqual(seen[-1]['max_tokens'], 32768)
                self.assertEqual(seen[-1]['stream_options'], {'include_usage': True})

    async def test_autodl_declared_disable_thinking_params_reach_agent(self):
        # All built-ins passed T5 without extensions. A deployment may explicitly
        # declare a tested strategy; both supported parameter shapes must survive.
        for strategy, value in [('enable_thinking', False), ('thinking', {'type': 'disabled'})]:
            with self.subTest(strategy=strategy), tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete_on_close=False) as file:
                json.dump({'models': [{
                    'id': 'autodl/Kimi-K2.5', 'provider_id': 'autodl', 'upstream_model': 'Kimi-K2.5',
                    'label': 'Kimi', 'capabilities': {'tool_calling': True, 'thinking': strategy},
                    'request_params': {strategy: value},
                }]}, file)
                file.flush()
                with patch.dict(os.environ, {'AUTODL_API_KEY': 'autodl-private',
                                             'AI_MODEL_REGISTRY_FILE': file.name}, clear=True):
                    registry = load_registry()
                seen = []

                def handler(request):
                    seen.append(json.loads(request.content))
                    return httpx.Response(200, text=sse({'content': 'ok'}))

                provider = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
                _ = [e async for e in provider.stream(ModelRequest('autodl/Kimi-K2.5', []))]
                self.assertEqual(seen[0][strategy], value)

    async def test_three_providers_host_bearer_model_and_streaming(self):
        with patch.dict(os.environ, ENV, clear=True):
            registry = load_registry()
        seen = []
        def handler(request):
            seen.append((request.url.host, request.headers['authorization'], json.loads(request.content)))
            return httpx.Response(200, text=sse({'content': '正文', 'reasoning_content': '思考'}))
        agent = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
        for model, host, key in [('qwen-plus', 'dashscope.aliyuncs.com', 'dash-secret'),
                                 ('deepseek-chat', 'api.deepseek.com', 'deep-secret'),
                                 ('glm-4-plus', 'open.bigmodel.cn', 'glm-secret')]:
            result = [event async for event in agent.stream(ModelRequest(model, []))]
            self.assertIn(TextDelta('正文'), result)
            actual_host, bearer, payload = seen[-1]
            self.assertEqual((actual_host, bearer, payload['model']), (host, f'Bearer {key}', model))
        self.assertEqual(seen[0][2]['max_tokens'], 32768)
        self.assertNotIn('enable_thinking', seen[-1][2])
        self.assertNotIn('stream_options', seen[-1][2])

    async def test_glm_streaming_tool_fragments_and_budget(self):
        with patch.dict(os.environ, ENV, clear=True):
            registry = load_registry()
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, text=(
                sse({'tool_calls': [{'index': 0, 'id': 'call-1', 'function': {'name': 'echo', 'arguments': '{"x":'}}]}, None).split('data: [DONE]')[0]
                + sse({'tool_calls': [{'index': 0, 'function': {'arguments': '1}'}}]}, 'tool_calls')))
        provider = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
        events = [event async for event in provider.stream(ModelRequest('glm-4-plus', [], tools=[{'type': 'function'}], max_tokens=123))]
        call = next(event.call for event in events if isinstance(event, ToolCallEvent))
        self.assertEqual((call.call_id, call.name, call.arguments), ('call-1', 'echo', {'x': 1}))
        self.assertEqual(seen[0]['max_tokens'], 123)
        self.assertEqual(seen[0]['tool_choice'], 'auto')

    async def test_fourth_provider_and_duplicate_upstream_without_business_changes(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete_on_close=False) as file:
            json.dump({'providers': [{'id': 'fourth', 'base_url': 'https://fourth.example/v1', 'api_key_env': 'FOURTH_KEY'}],
                       'models': [{'id': 'fourth/deepseek-chat', 'provider_id': 'fourth', 'upstream_model': 'deepseek-chat',
                                   'brand': 'deepseek', 'label': 'Fourth DeepSeek', 'capabilities': {'tool_calling': True}}],
                       'aliases': {'historical-id': 'fourth/deepseek-chat'}}, file)
            file.flush()
            with patch.dict(os.environ, {**ENV, 'AI_MODEL_REGISTRY_FILE': file.name, 'FOURTH_KEY': 'fourth-secret'}, clear=True):
                registry = load_registry()
                runtime = AgentRuntime(model='historical-id')
                self.assertEqual(runtime.model, 'fourth/deepseek-chat')
            seen = []
            def handler(request):
                seen.append((request.url.host, request.headers['authorization'], json.loads(request.content)['model']))
                return httpx.Response(200, text=sse({'content': 'ok'}))
            for model, host, key in [('deepseek-chat', 'api.deepseek.com', 'deep-secret'),
                                     ('historical-id', 'fourth.example', 'fourth-secret')]:
                agent = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
                _ = [event async for event in agent.stream(ModelRequest(model, []))]
                self.assertEqual(seen[-1], (host, f'Bearer {key}', 'deepseek-chat'))

    async def test_arbitrary_400_not_retried_and_upstream_secrets_not_logged(self):
        with patch.dict(os.environ, ENV, clear=True):
            registry = load_registry()
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(400, text='dash-secret invalid message sequence')
        provider = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler), retry_delay=0)
        with self.assertLogs('app.agent', level='WARNING') as captured:
            with self.assertRaises(BusinessError) as error:
                _ = [event async for event in provider.stream(ModelRequest('qwen-plus', []))]
        self.assertEqual(len(requests), 1)
        self.assertNotIn('dash-secret', error.exception.message + str(captured.output))

    async def test_runtime_rejects_unknown_or_no_tools(self):
        with patch.dict(os.environ, {**ENV, 'AI_ALLOWED_MODELS': 'deepseek-r1'}, clear=True):
            for model in ['missing', 'deepseek-r1']:
                with self.subTest(model=model), self.assertRaises(BusinessError):
                    AgentRuntime(model=model)

    async def test_new_glm_version_uses_explicit_capabilities_and_vendor_strategy(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete_on_close=False) as file:
            json.dump({'models': [{'id': 'zhipu/future-glm', 'provider_id': 'zhipu',
                                   'upstream_model': 'future-glm', 'label': 'GLM Custom', 'brand': 'zhipu',
                                   'capabilities': {'tool_calling': True, 'temperature': False,
                                                    'thinking': 'thinking', 'max_output_tokens': 777},
                                   'request_params': {'thinking': {'type': 'disabled'}}}]}, file)
            file.flush()
            with patch.dict(os.environ, {**ENV, 'ZHIPU_MODEL': 'future-glm',
                                         'AI_MODEL_REGISTRY_FILE': file.name}, clear=True):
                registry = load_registry()
            seen = []
            def handler(request):
                seen.append(json.loads(request.content))
                return httpx.Response(200, text=sse({'content': 'ok'}))
            agent = OpenAICompatProvider(registry=registry, transport=httpx.MockTransport(handler))
            _ = [event async for event in agent.stream(ModelRequest('zhipu/future-glm', [], temperature=1.0))]
            for payload in seen:
                self.assertEqual(payload['model'], 'future-glm')
                self.assertEqual(payload['thinking'], {'type': 'disabled'})
                self.assertEqual(payload['max_tokens'], 777)
                self.assertNotIn('temperature', payload)
                self.assertNotIn('enable_thinking', payload)
                self.assertNotIn('stream_options', payload)
