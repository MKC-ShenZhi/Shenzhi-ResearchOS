import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.core.errors import BusinessError
from app.integrations.llm.registry import Catalog, ModelRegistry, RegistryConfigError
from app.integrations.llm.resolver import load_registry


class RegistryTests(unittest.TestCase):
    def load(self, env):
        with patch.dict(os.environ, env, clear=True):
            return load_registry()

    def test_legacy_dashscope_and_deepseek_defaults(self):
        for env, model, provider in [
            ({'DASHSCOPE_API_KEY': 'dash'}, 'qwen-plus', 'dashscope'),
            ({'DEEPSEEK_API_KEY': 'deep'}, 'deepseek-chat', 'deepseek'),
            ({'DASHSCOPE_API_KEY': 'dash', 'DEEPSEEK_API_KEY': 'deep'}, 'qwen-plus', 'dashscope'),
        ]:
            registry = self.load(env)
            resolved = registry.resolve_model(None)
            self.assertEqual((resolved.spec.id, resolved.provider.spec.id), (f'{provider}/{model}', provider))

    def test_legacy_allowed_models_belong_to_legacy_provider(self):
        registry = self.load({'DASHSCOPE_API_KEY': 'dash', 'DEEPSEEK_API_KEY': 'deep',
                              'AI_ALLOWED_MODELS': 'deepseek-chat,deepseek-r1'})
        self.assertEqual(registry.resolve_model('deepseek-chat').provider.spec.id, 'dashscope')
        self.assertEqual(registry.resolve_model('deepseek/deepseek-chat').provider.spec.id, 'deepseek')
        self.assertEqual(registry.resolve_model('deepseek-r1').spec.brand, 'deepseek')

    def test_same_upstream_different_providers(self):
        registry = self.load({'DASHSCOPE_API_KEY': 'dash', 'DEEPSEEK_API_KEY': 'deep',
                              'DASHSCOPE_MODEL': 'shared', 'DEEPSEEK_MODEL': 'shared'})
        self.assertEqual(registry.resolve_model('shared').provider.spec.id, 'dashscope')
        self.assertEqual(registry.resolve_model('deepseek/shared').upstream_model, 'shared')

    def test_zhipu_requires_model_and_key_and_unknown_has_no_tools(self):
        registry = self.load({'ZHIPU_API_KEY': 'glm'})
        self.assertFalse(any(item.provider_id == 'zhipu' for item in registry.list_models()))
        registry = self.load({'ZHIPU_API_KEY': 'glm', 'ZHIPU_MODEL': 'custom-glm'})
        self.assertEqual(registry.default_model().id, 'zhipu/custom-glm')
        with self.assertRaisesRegex(BusinessError, 'Tool Calling'):
            registry.resolve_model('custom-glm', 'agent')
        registry = self.load({'ZHIPU_MODEL': 'glm-4-plus'})
        with self.assertRaisesRegex(BusinessError, '凭据'):
            registry.resolve_model('glm-4-plus')

    def test_invalid_and_unsupported_models(self):
        registry = self.load({'DEEPSEEK_API_KEY': 'deep', 'AI_ALLOWED_MODELS': 'deepseek-reasoner'})
        for model, purpose, message in [('missing', 'chat', '未注册'),
                                        ('deepseek-reasoner', 'agent', 'Tool Calling'),
                                        ('qwen-plus', 'chat', '凭据')]:
            with self.subTest(model=model), self.assertRaisesRegex(BusinessError, message):
                registry.resolve_model(model, purpose)

    def test_invalid_catalogs_fail_closed(self):
        provider = dict(id='p', base_url='https://test.example/v1', api_key_env='P_KEY')
        model = dict(id='m', provider_id='p', upstream_model='u', label='M')
        for data in [
            dict(providers=[provider, provider], models=[model]),
            dict(providers=[provider], models=[model, model]),
            dict(providers=[], models=[model]),
            dict(providers=[provider], models=[model], defaults={'chat': 'missing'}),
            dict(providers=[provider], models=[model], defaults={'agent': 'm'}),
            dict(providers=[provider], models=[model], aliases={'m': 'm'}),
        ]:
            with self.subTest(data=data), self.assertRaises(RegistryConfigError):
                ModelRegistry(Catalog.model_validate(data), {})

    def test_custom_catalog_defaults_aliases_and_disabled(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as file:
            json.dump({'providers': [{'id': 'fourth', 'base_url': 'https://fourth.example/v1', 'api_key_env': 'FOURTH_KEY'}],
                       'models': [{'id': 'fourth/m', 'provider_id': 'fourth', 'upstream_model': 'm',
                                   'label': 'Fourth', 'capabilities': {'tool_calling': True}},
                                  {'id': 'disabled', 'provider_id': 'fourth', 'upstream_model': 'm',
                                   'label': 'Disabled', 'enabled': False}],
                       'aliases': {'old-session-model': 'fourth/m'}, 'defaults': {'chat': 'fourth/m'}}, file)
            file.flush()
            registry = self.load({'AI_MODEL_REGISTRY_FILE': file.name, 'FOURTH_KEY': 'secret'})
            self.assertEqual(registry.resolve_model('old-session-model').spec.id, 'fourth/m')
            with self.assertRaisesRegex(BusinessError, '禁用'):
                registry.resolve_model('disabled')
            registry = self.load({'AI_MODEL_REGISTRY_FILE': file.name, 'AI_DEFAULT_MODEL': 'deepseek-chat'})
            self.assertEqual(registry.default_model().id, 'deepseek/deepseek-chat')

    def test_invalid_default_and_url_are_configuration_errors(self):
        for env in [{'AI_DEFAULT_MODEL': 'missing'}, {'DEEPSEEK_BASE_URL': 'http://untrusted.example'},
                    {'AI_AGENT_DEFAULT_MODEL': 'deepseek-reasoner'},
                    {'DEEPSEEK_BASE_URL': 'https://test.example:invalid'},
                    {'DEEPSEEK_BASE_URL': 'https://user:password@test.example'},
                    {'DEEPSEEK_BASE_URL': 'https://test.example/v1?api_key=private'}]:
            with self.subTest(env=env), self.assertRaises(RegistryConfigError):
                self.load(env)

    def test_no_secrets_in_public_catalog_or_repr(self):
        registry = self.load({'DEEPSEEK_API_KEY': 'SECRET_VALUE'})
        resolved = registry.resolve_model('deepseek-chat')
        self.assertNotIn('SECRET_VALUE', repr(resolved))
        self.assertNotIn('SECRET_VALUE', json.dumps(registry.public_models('chat')))

    def test_qualified_model_keeps_provider_when_legacy_priority_changes(self):
        env = {'DASHSCOPE_API_KEY': 'dash', 'DEEPSEEK_API_KEY': 'deep',
               'DASHSCOPE_MODEL': 'shared', 'DEEPSEEK_MODEL': 'shared'}
        first = self.load(env)
        second = self.load({**env, 'DASHSCOPE_API_KEY': ''})
        self.assertEqual(first.resolve_model('deepseek/shared').provider.spec.id, 'deepseek')
        self.assertEqual(second.resolve_model('deepseek/shared').provider.spec.id, 'deepseek')
        with self.assertRaisesRegex(BusinessError, '凭据'):
            second.resolve_model('dashscope/shared')

    def test_file_duplicate_ids_and_invalid_params_fail_without_input_leak(self):
        provider = {'id': 'p', 'base_url': 'https://p.example', 'api_key_env': 'P_KEY'}
        model = {'id': 'm', 'provider_id': 'p', 'upstream_model': 'm', 'label': 'M'}
        for data in [
            {'providers': [provider], 'models': [model, model]},
            {'providers': [provider, provider], 'models': [model]},
            {'providers': [provider], 'models': [{**model, 'request_params': {'api_key': 'PRIVATE_INPUT'}}]},
            {'providers': [{**provider, 'protocol': 'unsupported'}], 'models': [model]},
            {'providers': [provider], 'models': [{**model, 'capabilities': {'thinking': 'none'},
                                                  'request_params': {'enable_thinking': True}}]},
        ]:
            with self.subTest(data=data), tempfile.NamedTemporaryFile(mode='w', suffix='.json') as file:
                json.dump(data, file)
                file.flush()
                with self.assertRaises(RegistryConfigError) as error:
                    self.load({'AI_MODEL_REGISTRY_FILE': file.name})
                self.assertNotIn('PRIVATE_INPUT', str(error.exception))

    def test_fourth_provider_alone_can_supply_default_without_old_keys(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as file:
            json.dump({'providers': [{'id': 'fourth', 'base_url': 'https://fourth.example', 'api_key_env': 'FOURTH_KEY'}],
                       'models': [{'id': 'fourth/m', 'provider_id': 'fourth', 'upstream_model': 'm', 'label': 'M',
                                   'capabilities': {'tool_calling': True}}]}, file)
            file.flush()
            registry = self.load({'AI_MODEL_REGISTRY_FILE': file.name, 'FOURTH_KEY': 'key'})
            self.assertEqual(registry.default_model('chat').id, 'fourth/m')
            self.assertEqual(registry.default_model('agent').id, 'fourth/m')
