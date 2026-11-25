import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from agent_app.errors import BusinessError
from agent_app.integrations.llm.registry import Catalog, ModelRegistry, RegistryConfigError
from agent_app.integrations.llm.resolver import load_registry

VERIFIED_AUTODL_UPSTREAMS = ('DeepSeek-V4.1-Flash-1017', 'Qwen3.5-397B-A17B', 'Kimi-K2.5')


@contextmanager
def json_catalog(data):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'catalog.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        yield str(path)


class RegistryTests(unittest.TestCase):
    def load(self, env):
        with patch.dict(os.environ, env, clear=True):
            return load_registry()

    def test_all_builtins_key_only_and_stable_multi_provider_order(self):
        expected = {'dashscope': ['qwen-plus'], 'deepseek': ['deepseek-chat'],
                    'zhipu': ['glm-4-plus'], 'autodl': list(VERIFIED_AUTODL_UPSTREAMS), 'openlux': ['deepseek-v4.1-flash', 'qwen3.8-flash', 'glm-5.3-flash', 'kimi-k2.6']}
        for provider, upstreams in expected.items():
            with self.subTest(provider=provider):
                registry = self.load({f'{provider.upper()}_API_KEY': 'private'})
                actual = [m['value'] for m in registry.public_models('agent') if m['enabled']]
                self.assertEqual(actual, [f'{provider}/{m}' for m in upstreams])
                self.assertEqual(registry.public_default('agent'), actual[0] if actual else None)
        keys = {f'{p.upper()}_API_KEY': 'private' for p in expected}
        registry = self.load(keys)
        self.assertEqual(registry.public_default('agent'), 'dashscope/qwen-plus')
        self.assertEqual(len([m for m in registry.public_models('agent') if m['enabled']]), 10)
        for model in registry.models.values():
            if not model.enabled:
                with self.assertRaisesRegex(BusinessError, '禁用'):
                    registry.resolve_model(model.id)

    def test_catalog_extension_needs_no_resolver_branch(self):
        data = {'providers': [{'id': 'future', 'base_url': 'https://future.example/v1',
                               'api_key_env': 'UNUSUAL_CREDENTIAL'}],
                'models': [{'id': 'future/m', 'provider_id': 'future', 'upstream_model': 'm',
                            'label': 'Future', 'capabilities': {'tool_calling': True}}]}
        with json_catalog(data) as path, patch('agent_app.integrations.llm.resolver.CATALOG_PATH', Path(path)):
            registry = self.load({'UNUSUAL_CREDENTIAL': 'private'})
            self.assertEqual(registry.public_default('agent'), 'future/m')
            self.assertEqual(self.load({}).public_models('agent'), [])
            with self.assertRaisesRegex(BusinessError, '凭据'):
                self.load({}).resolve_model('future/m')

    def test_custom_replacement_preserves_default_order_and_explicit_missing_key_does_not_fallback(self):
        with json_catalog({'models': [{'id': 'dashscope/qwen-plus', 'provider_id': 'dashscope',
            'upstream_model': 'qwen-plus', 'label': 'Reviewed', 'capabilities': {'tool_calling': True}}]}) as path:
            registry = self.load({'AI_MODEL_REGISTRY_FILE': path, 'DASHSCOPE_API_KEY': 'dash',
                                  'DEEPSEEK_API_KEY': 'deep'})
            self.assertEqual(registry.public_default('agent'), 'dashscope/qwen-plus')
        registry = self.load({'AUTODL_API_KEY': 'private', 'AI_DEFAULT_MODEL': 'deepseek/deepseek-chat'})
        self.assertIsNone(registry.public_default('agent'))
        with self.assertRaisesRegex(BusinessError, '凭据'):
            registry.resolve_model(None, 'agent')

    def test_autodl_definitions_remain_without_key_and_unknown_requires_declaration(self):
        registry = self.load({})
        self.assertEqual([m.upstream_model for m in registry.models.values() if m.provider_id == 'autodl'],
                         list(VERIFIED_AUTODL_UPSTREAMS))
        self.assertEqual(registry.public_models('agent'), [])
        with self.assertRaisesRegex(BusinessError, '未注册'):
            self.load({'AUTODL_API_KEY': 'private'}).resolve_model('autodl/Untested-ID')
        with self.assertRaisesRegex(BusinessError, '未注册'):
            self.load({'AUTODL_API_KEY': 'private'}).resolve_model('Kimi-K2.5')

    def test_autodl_explicit_defaults_override_order_and_old_providers_keep_priority(self):
        env = {'AUTODL_API_KEY': 'autodl-private'}
        registry = self.load({**env, 'AI_DEFAULT_MODEL': 'autodl/Kimi-K2.5',
                              'AI_AGENT_DEFAULT_MODEL': 'autodl/Qwen3.5-397B-A17B'})
        self.assertEqual(registry.default_model().id, 'autodl/Kimi-K2.5')
        self.assertEqual(registry.default_model('agent').id, 'autodl/Qwen3.5-397B-A17B')
        for legacy, expected in [('DEEPSEEK_API_KEY', 'deepseek/deepseek-chat'),
                                 ('DASHSCOPE_API_KEY', 'dashscope/qwen-plus')]:
            self.assertEqual(self.load({**env, legacy: 'legacy-private'}).default_model().id, expected)

    def test_autodl_endpoint_override_is_https_and_uses_existing_validation(self):
        registry = self.load({'AUTODL_API_KEY': 'autodl-private', 'AUTODL_BASE_URL': 'https://proxy.example/v1/'})
        self.assertEqual(registry.resolve_model(None).base_url, 'https://proxy.example/v1')
        with self.assertRaises(RegistryConfigError):
            self.load({'AUTODL_API_KEY': 'autodl-private', 'AUTODL_BASE_URL': 'http://proxy.example/v1'})

    def test_public_catalog_hides_unconfigured_defaults_but_keeps_disabled_models(self):
        registry = self.load({})
        for purpose in ('chat', 'agent'):
            self.assertEqual(registry.public_models(purpose), [])
            self.assertIsNone(registry.public_default(purpose))
        registry = self.load({'AUTODL_API_KEY': 'autodl-private', 'AI_DEFAULT_MODEL': 'deepseek-chat'})
        self.assertIsNone(registry.public_default('chat'))
        self.assertTrue(registry.public_models('chat'))
        # Configured Provider with an explicitly disabled model retains the hint.
        registry = ModelRegistry(Catalog.model_validate({
            'providers': [{'id': 'p', 'base_url': 'https://p.example', 'api_key_env': 'P_KEY'}],
            'models': [{'id': 'disabled', 'provider_id': 'p', 'upstream_model': 'm',
                        'label': 'Disabled', 'enabled': False}],
        }), {'P_KEY': 'test-private'})
        self.assertEqual(registry.public_models('chat')[0]['reason'], 'model_disabled')
        self.assertFalse(registry.public_models('chat')[0]['enabled'])
        self.assertIsNone(registry.public_default('chat'))

    def test_legacy_dashscope_and_deepseek_defaults(self):
        for env, model, provider in [
            ({'DASHSCOPE_API_KEY': 'dash'}, 'qwen-plus', 'dashscope'),
            ({'DEEPSEEK_API_KEY': 'deep'}, 'deepseek-chat', 'deepseek'),
            ({'DASHSCOPE_API_KEY': 'dash', 'DEEPSEEK_API_KEY': 'deep'}, 'qwen-plus', 'dashscope'),
        ]:
            registry = self.load(env)
            resolved = registry.resolve_model(None)
            self.assertEqual((resolved.spec.id, resolved.provider.spec.id), (f'{provider}/{model}', provider))

    def test_same_upstream_different_providers(self):
        data = {'models': [{'id': f'{p}/shared', 'provider_id': p, 'upstream_model': 'shared',
                            'label': p} for p in ('dashscope', 'deepseek')],
                'aliases': {'shared': 'dashscope/shared'}}
        with json_catalog(data) as path:
            registry = self.load({'DASHSCOPE_API_KEY': 'dash', 'DEEPSEEK_API_KEY': 'deep',
                                  'AI_MODEL_REGISTRY_FILE': path})
            self.assertEqual(registry.resolve_model('shared').provider.spec.id, 'dashscope')
            self.assertEqual(registry.resolve_model('deepseek/shared').upstream_model, 'shared')
            registry = self.load({'DEEPSEEK_API_KEY': 'deep', 'AI_MODEL_REGISTRY_FILE': path})
            self.assertEqual(registry.resolve_model('shared', require_configured=False).provider.spec.id, 'dashscope')
            with self.assertRaisesRegex(BusinessError, '凭据'):
                registry.resolve_model('shared')
            self.assertEqual(registry.resolve_model('deepseek/shared').provider.spec.id, 'deepseek')

    def test_zhipu_key_only_and_unknown_requires_declaration(self):
        registry = self.load({'ZHIPU_API_KEY': 'glm'})
        self.assertEqual(registry.public_default('agent'), 'zhipu/glm-4-plus')
        with self.assertRaisesRegex(BusinessError, '未注册'):
            registry.resolve_model('zhipu/custom-glm')
        with self.assertRaisesRegex(BusinessError, '凭据'):
            self.load({}).resolve_model('glm-4-plus')

    def test_invalid_and_unsupported_models(self):
        registry = self.load({'DEEPSEEK_API_KEY': 'deep'})
        for model, purpose, message in [('missing', 'chat', '未注册'),
                                        ('deepseek-reasoner', 'agent', '禁用'),
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
        with json_catalog({'providers': [{'id': 'fourth', 'base_url': 'https://fourth.example/v1', 'api_key_env': 'FOURTH_KEY'}],
                       'models': [{'id': 'fourth/m', 'provider_id': 'fourth', 'upstream_model': 'm',
                                   'label': 'Fourth', 'capabilities': {'tool_calling': True}},
                                  {'id': 'disabled', 'provider_id': 'fourth', 'upstream_model': 'm',
                                   'label': 'Disabled', 'enabled': False}],
                       'aliases': {'old-session-model': 'fourth/m'}, 'defaults': {'chat': 'fourth/m'}}) as catalog_path:
            registry = self.load({'AI_MODEL_REGISTRY_FILE': catalog_path, 'FOURTH_KEY': 'secret'})
            self.assertEqual(registry.resolve_model('old-session-model').spec.id, 'fourth/m')
            with self.assertRaisesRegex(BusinessError, '禁用'):
                registry.resolve_model('disabled')
            registry = self.load({'AI_MODEL_REGISTRY_FILE': catalog_path, 'AI_DEFAULT_MODEL': 'deepseek-chat'})
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
        for keys in ({'DASHSCOPE_API_KEY': 'dash', 'DEEPSEEK_API_KEY': 'deep'},
                     {'DEEPSEEK_API_KEY': 'deep'}):
            registry = self.load(keys)
            self.assertEqual(registry.resolve_model('deepseek-chat').provider.spec.id, 'deepseek')
            self.assertEqual(registry.resolve_model('deepseek/deepseek-chat').provider.spec.id, 'deepseek')
        with self.assertRaisesRegex(BusinessError, '凭据'):
            self.load({'DEEPSEEK_API_KEY': 'deep'}).resolve_model('dashscope/qwen-plus')

    def test_file_duplicate_ids_and_invalid_params_fail_without_input_leak(self):
        provider = {'id': 'p', 'base_url': 'https://p.example', 'api_key_env': 'P_KEY'}
        model = {'id': 'm', 'provider_id': 'p', 'upstream_model': 'm', 'label': 'M'}
        for data in [
            {'providers': [provider], 'models': [model, model]},
            {'aliases': {'invalid-alias': 'unknown-model'}},
            {'providers': [provider, provider], 'models': [model]},
            {'providers': [provider], 'models': [{**model, 'request_params': {'api_key': 'PRIVATE_INPUT'}}]},
            {'providers': [{**provider, 'protocol': 'unsupported'}], 'models': [model]},
            {'providers': [provider], 'models': [{**model, 'capabilities': {'thinking': 'none'},
                                                  'request_params': {'enable_thinking': True}}]},
        ]:
            with self.subTest(data=data), json_catalog(data) as catalog_path:
                with self.assertRaises(RegistryConfigError) as error:
                    self.load({'AI_MODEL_REGISTRY_FILE': catalog_path})
                self.assertNotIn('PRIVATE_INPUT', str(error.exception))

    def test_fourth_provider_alone_can_supply_default_without_old_keys(self):
        with json_catalog({'providers': [{'id': 'fourth', 'base_url': 'https://fourth.example', 'api_key_env': 'FOURTH_KEY'}],
                           'models': [{'id': 'fourth/m', 'provider_id': 'fourth', 'upstream_model': 'm', 'label': 'M',
                                       'capabilities': {'tool_calling': True}}]}) as catalog_path:
            registry = self.load({'AI_MODEL_REGISTRY_FILE': catalog_path, 'FOURTH_KEY': 'key'})
            self.assertEqual(registry.default_model('chat').id, 'fourth/m')
            self.assertEqual(registry.default_model('agent').id, 'fourth/m')
