"""No native credentials: every runtime/config/key file lives in a temp tree."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

DOCKER = Path(__file__).resolve().parents[1]


class PrepareEnvTests(unittest.TestCase):
    def test_payment_secret_is_paired_and_preserved(self):
        self.run_setup(local=False)
        first = self.read('payment')['PAYMENT_SERVICE_TOKEN']
        self.assertTrue(first)
        self.assertEqual(first, self.read('backend')['PAYMENT_SERVICE_TOKEN'])
        self.assertEqual(self.read('payment')['WECHAT_ENABLED'], 'false')
        self.assertEqual(self.read('backend')['PAYMENT_SERVICE_URL'], 'http://payment:8090')
        self.run_setup(local=False)
        self.assertEqual(first, self.read('payment')['PAYMENT_SERVICE_TOKEN'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.here = self.root / 'infra/docker'
        (self.here / 'env').mkdir(parents=True)
        shutil.copyfile(DOCKER / '.env.example', self.here / '.env.example')
        for source in (DOCKER / 'env').glob('*.env.example'):
            shutil.copyfile(source, self.here / 'env' / source.name)
        spec = importlib.util.spec_from_file_location('prepare_env', DOCKER / 'prepare-env.py')
        self.env = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.env)
        self.env.HERE, self.env.ROOT = self.here, self.root

    def write(self, path, values):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.env.render(values))

    def docker(self, name, values):
        self.write(self.here / 'env' / f'{name}.env', values)

    def native(self, name, values):
        path = self.root / 'apps' / name / ('.env.local' if name == 'web' else '.env')
        self.write(path, values)

    def read(self, name):
        return self.env.read(self.here / 'env' / f'{name}.env')

    def run_setup(self, local=True):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.env.main(['--from-local'] if local else [])
        self.assertNotIn('fixture-secret', output.getvalue())

    def snapshot(self):
        return {path.relative_to(self.root): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def v2_native(self):
        self.native('backend', {
            'AGENT_V2_ADMISSION': 'authorized',
            'AGENT_GRANT_PRIVATE_KEY_FILE': 'fixture-private.pem',
            'AGENT_AUDIENCE': 'fixture-audience', 'AGENT_GRANT_ISSUER': 'fixture-issuer',
        })
        self.native('agent', {
            'AGENT_GRANT_PUBLIC_KEYS_FILE': 'fixture-public.json',
            'AGENT_AUDIENCE': 'fixture-audience', 'AGENT_GRANT_ISSUER': 'fixture-issuer',
        })
        # Deliberately fictitious, non-cryptographic fixtures. Never read real keys.
        (self.root / 'apps/backend/fixture-private.pem').write_text('fixture-secret-private')
        (self.root / 'apps/agent/fixture-public.json').write_text('{"fixture": "public"}')

    def test_first_init_and_idempotence_without_native_config(self):
        self.run_setup(local=False)
        first = self.snapshot()
        self.run_setup(local=False)
        self.assertEqual(self.snapshot(), first)
        self.assertTrue(self.read('web')['BETTER_AUTH_SECRET'])
        compose = self.env.read(self.here / '.env')
        self.assertGreaterEqual(len(compose['ADMIN_DEV_SESSION_SECRET']), 32)
        for name in ('web', 'backend', 'agent'):
            self.assertNotIn('ADMIN_DEV_SESSION_SECRET', self.read(name))
        self.assertEqual(self.read('web')['BACKEND_BFF_SECRET'], self.read('backend')['BACKEND_BFF_SECRET'])

    def test_template_comments_optional_overrides_and_extra_values_survive_setup(self):
        # Values containing raw env_file syntax must not be interpolated or quoted.
        literal = 'fixture-secret-$token#literal'
        self.docker('agent', {'CUSTOM_SETTING': literal})
        self.native('agent', {'DASHSCOPE_BASE_URL': 'https://provider.example/v1'})
        self.run_setup()
        path = self.here / 'env/agent.env'
        content = path.read_text(encoding='utf-8')
        self.assertIn('# ----', content)
        self.assertIn('DASHSCOPE_BASE_URL=https://provider.example/v1\n', content)
        self.assertNotIn('# DASHSCOPE_BASE_URL=', content)
        self.assertIn('# DEEPSEEK_BASE_URL=<DEEPSEEK_BASE_URL>', content)
        self.assertEqual(self.read('agent')['CUSTOM_SETTING'], literal)
        for name in ('web', 'backend', 'agent'):
            template = (self.here / 'env' / f'{name}.env.example').read_text(encoding='utf-8')
            generated = (self.here / 'env' / f'{name}.env').read_text(encoding='utf-8')
            for line in template.splitlines():
                if line.startswith('# ') and '=' not in line:
                    self.assertIn(line, generated)
        self.assertIn('# ', (self.here / '.env').read_text(encoding='utf-8'))
        before = self.snapshot()
        self.run_setup()
        self.assertEqual(before, self.snapshot())

    def test_empty_credentials_are_generated_and_shared(self):
        self.docker('web', {'BETTER_AUTH_SECRET': '', 'BACKEND_BFF_SECRET': ''})
        roles = ('AGENT_SERVICE_TOKEN', 'AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN', 'AGENT_CONTROL_TOKEN')
        self.docker('backend', dict.fromkeys((*roles, 'BACKEND_BFF_SECRET'), ''))
        self.docker('agent', dict.fromkeys((*roles, 'AGENT_WORKER_TOKEN'), ''))
        self.run_setup()
        agent = self.read('agent')
        for key in roles:
            self.assertTrue(agent[key])
            self.assertEqual(agent[key], self.read('backend')[key])
        self.assertEqual(len({agent[key] for key in (*roles, 'AGENT_WORKER_TOKEN')}), 5)
        self.assertTrue(self.read('web')['BETTER_AUTH_SECRET'])
        before = self.snapshot()
        self.run_setup()
        self.assertEqual(before, self.snapshot())

    def test_empty_values_import_native_without_modifying_native_files(self):
        self.native('web', {'BETTER_AUTH_SECRET': 'fixture-secret-auth', 'BACKEND_BFF_SECRET': 'fixture-secret-bff'})
        self.native('agent', {'AUTODL_API_KEY': 'fixture-secret-provider', 'AUTODL_BASE_URL': 'https://example.invalid/v1',
                              'AI_DEFAULT_MODEL': 'fixture-model', 'AGENT_WORKER_TOKEN': 'fixture-secret-worker'})
        self.docker('web', {'BETTER_AUTH_SECRET': '', 'BACKEND_BFF_SECRET': ''})
        self.docker('agent', {'AUTODL_API_KEY': '', 'AUTODL_BASE_URL': '', 'AI_DEFAULT_MODEL': '', 'AGENT_WORKER_TOKEN': ''})
        native_before = {p: p.read_bytes() for p in (self.root / 'apps').rglob('*') if p.is_file()}
        self.run_setup()
        self.assertEqual(self.read('web')['BETTER_AUTH_SECRET'], 'fixture-secret-auth')
        self.assertEqual(self.read('backend')['BACKEND_BFF_SECRET'], 'fixture-secret-bff')
        for key in ('AUTODL_API_KEY', 'AUTODL_BASE_URL', 'AI_DEFAULT_MODEL', 'AGENT_WORKER_TOKEN'):
            self.assertEqual(self.read('agent')[key], self.env.read(self.root / 'apps/agent/.env')[key])
        self.assertEqual(native_before, {p: p.read_bytes() for p in native_before})

    def test_existing_nonempty_docker_values_win_over_native(self):
        self.native('web', {'BETTER_AUTH_SECRET': 'fixture-secret-native', 'BACKEND_BFF_SECRET': 'fixture-secret-native-bff'})
        self.native('agent', {'AUTODL_BASE_URL': 'https://native.example.invalid', 'AI_DEFAULT_MODEL': 'native-model'})
        self.docker('web', {'BETTER_AUTH_SECRET': 'fixture-secret-docker', 'BACKEND_BFF_SECRET': 'fixture-secret-docker-bff'})
        self.docker('agent', {'AUTODL_BASE_URL': 'https://docker.example.invalid', 'AI_DEFAULT_MODEL': 'docker-model'})
        self.run_setup()
        self.assertEqual(self.read('web')['BETTER_AUTH_SECRET'], 'fixture-secret-docker')
        self.assertEqual(self.read('backend')['BACKEND_BFF_SECRET'], 'fixture-secret-docker-bff')
        self.assertEqual(self.read('agent')['AI_DEFAULT_MODEL'], 'docker-model')
        self.assertEqual(self.read('agent')['AUTODL_BASE_URL'], 'https://docker.example.invalid')
        before = self.snapshot()
        self.run_setup()
        self.assertEqual(before, self.snapshot())

    def test_openlux_import_and_existing_docker_values_are_preserved(self):
        native = {'OPENLUX_API_KEY': 'fixture-secret-openlux-native',
                  'OPENLUX_BASE_URL': 'https://native.example.invalid/v1'}
        self.native('agent', native)
        native_before = (self.root / 'apps/agent/.env').read_bytes()
        self.run_setup()
        for key, value in native.items():
            self.assertEqual(self.read('agent')[key], value)
            self.assertNotIn(key, self.read('web'))
            self.assertNotIn(key, self.read('backend'))
        docker_values = {**self.read('agent'), 'OPENLUX_API_KEY': 'fixture-secret-openlux-docker',
                         'OPENLUX_BASE_URL': 'https://docker.example.invalid/v1'}
        self.docker('agent', docker_values)
        self.run_setup()
        self.assertEqual(self.read('agent'), docker_values)
        # The first run restores template comments to the manually written file.
        before = self.snapshot()
        self.run_setup()
        self.assertEqual(before, self.snapshot())
        self.assertEqual((self.root / 'apps/agent/.env').read_bytes(), native_before)

    def test_all_role_tokens_import_native_into_empty_docker_values(self):
        roles = ('AGENT_SERVICE_TOKEN', 'AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN', 'AGENT_CONTROL_TOKEN')
        fixtures = {key: f'fixture-secret-{index}' for index, key in enumerate(roles)}
        self.native('backend', fixtures)
        self.native('agent', {**fixtures, 'AGENT_WORKER_TOKEN': 'fixture-secret-worker'})
        self.docker('backend', dict.fromkeys(roles, ''))
        self.docker('agent', dict.fromkeys((*roles, 'AGENT_WORKER_TOKEN'), ''))
        self.run_setup()
        for name in ('backend', 'agent'):
            for key, value in fixtures.items():
                self.assertEqual(self.read(name)[key], value)
        self.assertEqual(self.read('agent')['AGENT_WORKER_TOKEN'], 'fixture-secret-worker')

    def test_blank_provider_overrides_without_native_are_unset(self):
        self.docker('agent', {'AUTODL_BASE_URL': '', 'AI_DEFAULT_MODEL': ''})
        self.run_setup()
        self.assertNotIn('AUTODL_BASE_URL', self.read('agent'))
        self.assertEqual(self.read('agent')['AI_DEFAULT_MODEL'], '')

    def test_shared_credential_conflicts_fail_without_writes(self):
        for key in ('BACKEND_BFF_SECRET', 'AGENT_SERVICE_TOKEN', 'AGENT_GATEWAY_TOKEN',
                    'AGENT_FACT_READER_TOKEN', 'AGENT_CONTROL_TOKEN', 'AGENT_AUDIENCE', 'AGENT_GRANT_ISSUER'):
            with self.subTest(key=key):
                other = 'web' if key == 'BACKEND_BFF_SECRET' else 'agent'
                self.docker('backend', {key: 'fixture-secret-one'})
                self.docker(other, {key: 'fixture-secret-two'})
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, key):
                    self.run_setup()
                self.assertEqual(before, self.snapshot())
                (self.here / 'env/backend.env').unlink()
                (self.here / 'env' / f'{other}.env').unlink()

    def test_signing_missing_and_empty_paths_import_native_and_stay_idempotent(self):
        for configured in (None, ''):
            with self.subTest(configured=configured):
                self.v2_native()
                for name, key in (('backend', 'AGENT_GRANT_PRIVATE_KEY_FILE'), ('agent', 'AGENT_GRANT_PUBLIC_KEYS_FILE')):
                    self.docker(name, {key: configured, 'AGENT_AUDIENCE': '', 'AGENT_GRANT_ISSUER': ''}
                                if configured is not None else {})
                self.run_setup()
                self.assertEqual(self.read('backend')['AGENT_GRANT_PRIVATE_KEY_FILE'], '/run/secrets/backend/grant-private.pem')
                self.assertEqual(self.read('agent')['AGENT_GRANT_PUBLIC_KEYS_FILE'], '/run/secrets/agent/grant-public.json')
                self.assertEqual(self.read('backend')['AGENT_AUDIENCE'], 'fixture-audience')
                self.assertEqual(self.read('agent')['AGENT_GRANT_ISSUER'], 'fixture-issuer')
                before = self.snapshot()
                self.run_setup()
                self.assertEqual(before, self.snapshot())

    def test_empty_admission_identity_reuses_nonempty_docker_peer(self):
        self.native('agent', {'AGENT_AUDIENCE': 'native', 'AGENT_GRANT_ISSUER': 'native'})
        self.docker('backend', {'AGENT_AUDIENCE': 'docker', 'AGENT_GRANT_ISSUER': 'docker'})
        self.docker('agent', {'AGENT_AUDIENCE': '', 'AGENT_GRANT_ISSUER': ''})
        self.run_setup()
        self.assertEqual(self.read('agent')['AGENT_AUDIENCE'], 'docker')
        self.assertEqual(self.read('agent')['AGENT_GRANT_ISSUER'], 'docker')

    def test_existing_signing_files_reused_when_paths_empty_and_native_absent(self):
        for name, filename in (('backend', 'grant-private.pem'), ('agent', 'grant-public.json')):
            path = self.here / 'secrets' / name / filename
            path.parent.mkdir(parents=True)
            path.write_text('fixture-existing-signing-file')
        self.docker('backend', {'AGENT_V2_ADMISSION': 'authorized', 'AGENT_GRANT_PRIVATE_KEY_FILE': ''})
        self.docker('agent', {'AGENT_GRANT_PUBLIC_KEYS_FILE': ''})
        self.run_setup()
        self.assertEqual(self.read('backend')['AGENT_GRANT_PRIVATE_KEY_FILE'], '/run/secrets/backend/grant-private.pem')
        before = self.snapshot()
        self.run_setup()
        self.assertEqual(before, self.snapshot())

    def test_valid_custom_signing_paths_preserved(self):
        self.v2_native()
        private = self.root / 'custom-private.pem'
        public = self.root / 'custom-public.json'
        private.write_text('fixture-secret-custom')
        public.write_text('fixture-public-custom')
        self.docker('backend', {'AGENT_GRANT_PRIVATE_KEY_FILE': str(private)})
        self.docker('agent', {'AGENT_GRANT_PUBLIC_KEYS_FILE': str(public)})
        self.run_setup()
        self.assertEqual(self.read('backend')['AGENT_GRANT_PRIVATE_KEY_FILE'], str(private))
        self.assertEqual(self.read('agent')['AGENT_GRANT_PUBLIC_KEYS_FILE'], str(public))
        self.assertFalse((self.here / 'secrets/backend/grant-private.pem').exists())

    def test_missing_empty_or_invalid_signing_file_fails_without_partial_copy(self):
        self.v2_native()
        public = self.root / 'apps/agent/fixture-public.json'
        for failure in ('missing', 'empty', 'directory'):
            with self.subTest(failure=failure):
                if public.is_file():
                    public.unlink()
                if failure == 'empty':
                    public.write_text('')
                elif failure == 'directory':
                    public.mkdir()
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, 'AGENT_GRANT_PUBLIC_KEYS_FILE'):
                    self.run_setup()
                self.assertEqual(before, self.snapshot())
                self.assertFalse((self.here / 'secrets/backend/grant-private.pem').exists())

    def test_nonempty_broken_docker_signing_path_not_silently_replaced(self):
        self.v2_native()
        self.docker('backend', {'AGENT_GRANT_PRIVATE_KEY_FILE': '/run/secrets/backend/missing.pem'})
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'AGENT_GRANT_PRIVATE_KEY_FILE'):
            self.run_setup()
        self.assertEqual(before, self.snapshot())

    def test_disabled_v2_needs_no_keys_but_enabled_v2_missing_keys_fails(self):
        self.run_setup()
        self.assertEqual(self.read('backend')['AGENT_GRANT_PRIVATE_KEY_FILE'], '')
        self.docker('backend', {'AGENT_V2_ADMISSION': 'authorized'})
        self.docker('agent', {})
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'V2 signing keys required'):
            self.run_setup()
        self.assertEqual(before, self.snapshot())

    def test_retired_protocol_settings_are_dropped_from_generated_environment(self):
        self.v2_native()
        self.docker('agent', {'AGENT_V1_ADMISSION': 'legacy', 'AGENT_WORKER_PROTOCOL': '1'})
        self.run_setup()
        generated = self.read('agent')
        self.assertNotIn('AGENT_V1_ADMISSION', generated)
        self.assertNotIn('AGENT_WORKER_PROTOCOL', generated)

    def test_publication_io_failure_restores_existing_files(self):
        self.run_setup()
        self.docker('web', {'BETTER_AUTH_SECRET': ''})
        self.docker('backend', {'BACKEND_BFF_SECRET': ''})
        before = self.snapshot()
        real_replace = os.replace
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('fixture publication failure')
            return real_replace(source, destination)

        with patch.object(self.env.os, 'replace', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'fixture publication failure'):
                self.run_setup()
        self.assertEqual(before, self.snapshot())

    def test_publication_failure_removes_new_signing_copies(self):
        self.v2_native()
        before = self.snapshot()
        real_replace = os.replace
        calls = 0

        def fail_third(source, destination):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('fixture publication failure')
            return real_replace(source, destination)

        with patch.object(self.env.os, 'replace', side_effect=fail_third):
            with self.assertRaisesRegex(OSError, 'fixture publication failure'):
                self.run_setup()
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
