import os
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.core.admin_auth import PATH, COOKIE


class AdminConsoleTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'ADMIN_AUTH_MODE': 'local_password', 'ADMIN_LOCAL_USERNAME': 'admin',
            'ADMIN_LOCAL_PASSWORD': '123456', 'ADMIN_SESSION_SECRET': 's' * 32,
            'ADMIN_SESSION_TTL_SECONDS': '28800', 'ADMIN_AUTH_LOCAL_ONLY': 'true',
            'AGENT_INTERNAL_URL': 'http://127.0.0.1:8001', 'AGENT_SERVICE_TOKEN': 'test-token',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app, client=('127.0.0.1', 5555))

    def login(self, client=None, password='123456'):
        return (client or self.client).post(PATH + '/auth/login', json={'username': 'admin', 'password': password})

    def test_login_cookie_logout(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        cookie = response.headers['set-cookie']
        for flag in ['HttpOnly', 'SameSite=strict', 'Path=' + PATH]:
            self.assertIn(flag, cookie)
        self.assertEqual(self.client.get(PATH + '/auth/me').json()['data']['username'], 'admin')
        self.assertEqual(self.client.post(PATH + '/auth/logout').status_code, 200)
        self.assertEqual(self.client.get(PATH + '/auth/me').status_code, 401)

    def test_wrong_and_missing_configuration(self):
        self.assertEqual(self.login(password='wrong').status_code, 401)
        for key in ['ADMIN_SESSION_SECRET', 'ADMIN_LOCAL_USERNAME', 'ADMIN_LOCAL_PASSWORD', 'ADMIN_AUTH_MODE']:
            with patch.dict(os.environ, {key: ''}):
                self.assertEqual(self.login().status_code, 503)

    def test_protected_and_no_store(self):
        for path in ['/users', '/capabilities', '/auth/me']:
            r = self.client.get(PATH + path, headers={'x-shenzhi-user-id': 'admin'})
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.headers['cache-control'], 'no-store')
        r = self.client.post(PATH + '/auth/login', json={})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.headers['cache-control'], 'no-store')

    def test_tampering_expiry_and_rotation(self):
        with patch('app.core.admin_auth.time.time', return_value=1000):
            self.login()
        token = self.client.cookies.get(COOKIE)
        self.client.cookies.set(COOKIE, token + 'x', domain='testserver.local', path=PATH)
        self.assertEqual(self.client.get(PATH + '/auth/me').status_code, 401)
        self.client.cookies.clear()
        with patch('app.core.admin_auth.time.time', return_value=1000):
            self.login()
        with patch('app.core.admin_auth.time.time', return_value=30000):
            self.assertEqual(self.client.get(PATH + '/auth/me').status_code, 401)
        self.login()
        with patch.dict(os.environ, {'ADMIN_LOCAL_PASSWORD': 'rotated'}):
            self.assertEqual(self.client.get(PATH + '/auth/me').status_code, 401)

    def test_remote_and_https(self):
        remote = TestClient(app, client=('203.0.113.1', 5555))
        self.assertEqual(self.login(remote).status_code, 403)
        self.assertEqual(remote.get(PATH + '/users', headers={'x-forwarded-for': '127.0.0.1'}).status_code, 403)
        https = TestClient(app, base_url='https://testserver', client=('::1', 5555))
        self.assertIn('Secure', self.login(https).headers['set-cookie'])

    def test_capabilities_real_projection_and_failures(self):
        self.login()
        payload = {'models': [{'value':'test/model','label':'Test','provider':'test','enabled':True}],
                   'default_model':'test/model', 'skills':[{'name':'test-skill','description':'test'}]}
        with patch('app.integrations.admin_console.capabilities.httpx.AsyncClient.get', new=AsyncMock(return_value=httpx.Response(200, json=payload, request=httpx.Request('GET','http://test')))) as call:
            r = self.client.get(PATH + '/capabilities')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['data']['models'], payload['models'])
            self.assertEqual(r.json()['data']['tools_status'], 'not_connected')
            self.assertEqual(call.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')
        with patch('app.integrations.admin_console.capabilities.httpx.AsyncClient.get', new=AsyncMock(side_effect=httpx.ConnectError('offline'))):
            self.assertEqual(self.client.get(PATH + '/capabilities').status_code, 503)
        with patch.dict(os.environ, {'AGENT_SERVICE_TOKEN':''}):
            self.assertEqual(self.client.get(PATH + '/capabilities').status_code, 503)

    def test_users_reuses_service(self):
        self.login()
        payload = dict(items=[], total=0, page=2, page_size=20, plans=['free'],
                       stats=dict(total_users=3, free_users=2, abnormal_users=1),
                       updated_at='2026-11-20T00:00:00Z', usage_status='near_realtime',
                       usage_note='Partial 为已知下界；未知用量保留预留')
        scope = MagicMock()
        scope.__aenter__ = AsyncMock(return_value='db')
        scope.__aexit__ = AsyncMock(return_value=False)
        with patch('app.api.admin_console.session_scope', return_value=scope), patch(
                'app.api.admin_console.list_users', new=AsyncMock(return_value=payload)) as service:
            response = self.client.get(PATH + '/users?page=2&search=%20name%20&plan_id=free')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['stats'], payload['stats'])
        service.assert_awaited_once_with('db', page=2, page_size=20, search='name', plan_id='free')

    def test_old_admin_routes_removed(self):
        self.login()
        for path in ['/api/v1/admin/users', '/api/v1/admin/access']:
            self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == '__main__':
    unittest.main()
