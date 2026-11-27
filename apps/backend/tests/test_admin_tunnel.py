import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.admin_auth import COOKIE, PATH


class AdminTunnelTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        secret = Path(self.directory.name) / 'entry'
        secret.write_text('a' * 64, encoding='utf-8')
        self.env = patch.dict(os.environ, dict(ADMIN_AUTH_MODE='ssh_tunnel', ADMIN_AUTH_LOCAL_ONLY='true',
            ADMIN_ENTRY_SECRET_FILE=str(secret), ADMIN_TUNNEL_PRINCIPAL='operator', ADMIN_SESSION_SECRET='s' * 40))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app, base_url='http://127.0.0.1:3101', client=('127.0.0.1', 1234))
        self.addCleanup(self.client.close)
        self.entry = {'X-ShenZhi-Admin-Entry': 'a' * 64}

    def test_trusted_entry_bootstraps_cookie_and_public_entry_is_denied(self):
        self.assertEqual(self.client.get(PATH + '/auth/me').status_code, 403)
        response = self.client.get(PATH + '/auth/me', headers=self.entry)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['username'], 'operator')
        self.assertIn(COOKIE, response.cookies)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
        self.assertEqual(self.client.get(PATH + '/auth/me', headers={**self.entry, 'Host': 'public.example.invalid'}).status_code, 403)
        self.assertEqual(self.client.get(PATH + '/auth/me', headers={**self.entry, 'Origin': 'https://evil.example.invalid'}).status_code, 403)
        self.assertEqual(self.client.get(PATH + '/auth/me', headers={**self.entry, 'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.post(PATH + '/auth/logout', headers=self.entry).status_code, 200)
        self.assertEqual(self.client.post(PATH + '/auth/login', json={'username': 'operator', 'password': 'anything'}, headers=self.entry).status_code, 403)

    def test_cookie_requires_entry_on_every_request_and_secret_rotation_invalidates_it(self):
        self.client.get(PATH + '/auth/me', headers=self.entry)
        self.assertEqual(self.client.post(PATH + '/auth/logout').status_code, 403)
        with patch.dict(os.environ, {'ADMIN_ENTRY_SECRET_FILE': str(Path(self.directory.name) / 'missing')}):
            self.assertEqual(self.client.get(PATH + '/auth/me', headers=self.entry).status_code, 503)
        self.assertEqual(self.client.post(PATH + '/auth/logout', headers={**self.entry, 'X-ShenZhi-Admin-Entry': 'b' * 64}).status_code, 403)

    def test_invalid_candidate_never_echoes_submitted_secret(self):
        self.client.get(PATH + '/auth/me', headers=self.entry)
        secret = 'synthetic-value-must-never-be-echoed'
        response = self.client.post(PATH + '/agent/config/preview',
            headers={**self.entry, 'X-Admin-Request': '1'}, json={'spec': {'api_key': secret}})
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(secret, response.text)

    def test_real_entry_secret_rotation_invalidates_existing_cookie(self):
        self.client.get(PATH + '/auth/me', headers=self.entry)
        (Path(self.directory.name) / 'entry').write_text('b' * 64, encoding='utf-8')
        rotated = {'X-ShenZhi-Admin-Entry': 'b' * 64}
        self.assertEqual(self.client.get(PATH + '/agent/providers', headers=self.entry).status_code, 403)
        self.assertEqual(self.client.get(PATH + '/agent/providers', headers=rotated).status_code, 401)
        self.assertEqual(self.client.get(PATH + '/auth/me', headers=rotated).status_code, 200)

    def test_untrusted_peer_and_cross_site_write_are_denied(self):
        with TestClient(app, base_url='http://127.0.0.1:3101', client=('203.0.113.10', 1234)) as remote:
            self.assertEqual(remote.get(PATH + '/auth/me', headers=self.entry).status_code, 403)
        self.client.get(PATH + '/auth/me', headers=self.entry)
        self.assertEqual(self.client.post(PATH + '/auth/logout', headers={**self.entry,
            'Origin': 'https://evil.example.invalid', 'X-Admin-Request': '1'}).status_code, 403)
