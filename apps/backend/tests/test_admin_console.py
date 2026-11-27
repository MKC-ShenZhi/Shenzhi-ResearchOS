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

    def test_docker_development_credentials_are_rejected_outside_development(self):
        with patch.dict(os.environ, {'ADMIN_LOCAL_USERNAME': 'shenzhi', 'ADMIN_LOCAL_PASSWORD': 'shenzhi-dev'}):
            for environment in ('', 'production', 'staging'):
                with patch.dict(os.environ, {'ENVIRONMENT': environment}):
                    response = self.client.post(PATH + '/auth/login', json={'username': 'shenzhi', 'password': 'shenzhi-dev'})
                    self.assertEqual(response.status_code, 503)
            with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
                response = self.client.post(PATH + '/auth/login', json={'username': 'shenzhi', 'password': 'shenzhi-dev'})
                self.assertEqual(response.status_code, 200)

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
            self.assertTrue(call.call_args.args[0].endswith('/internal/v2/config'))
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

    def test_write_routes_require_independent_session_and_same_origin_header(self):
        paths=['/plans/publish','/entitlements/assign','/migration/preview','/grants/test-grant/reconcile-close']
        for path in paths:
            r=self.client.post(PATH+path,json={},headers={'x-shenzhi-user-id':'admin','x-admin-request':'1'})
            self.assertEqual(r.status_code,401)
        self.login()
        for path in paths:
            self.assertEqual(self.client.post(PATH+path,json={}).status_code,403)
            self.assertEqual(self.client.post(PATH+path,json={},headers={'x-admin-request':'1','sec-fetch-site':'cross-site'}).status_code,403)

    def test_admin_assignment_route_preserves_principal_and_operation(self):
        self.login()
        body=dict(operation_id='test-write-operation',reason='test assignment',user_ids=['test-user'],
                  plan_id='basic',policy_revision='basic-v1-test',preview=False)
        scope=MagicMock();scope.__aenter__=AsyncMock(return_value='db');scope.__aexit__=AsyncMock(return_value=False)
        result={'preview':False,'items':[{'user_id':'test-user','status':'success'}]}
        with patch('app.api.admin_console.session_scope',return_value=scope), patch(
                'app.api.admin_console.plan_admin.assign',new=AsyncMock(return_value=result)) as assign:
            response=self.client.post(PATH+'/entitlements/assign',json=body,headers={'x-admin-request':'1'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['data'],result)
        self.assertEqual(assign.call_args.args[2],'local-admin:admin')
        self.assertEqual(assign.call_args.args[1].operation_id,body['operation_id'])
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_old_admin_routes_removed(self):
        self.login()
        for path in ['/api/v1/admin/users', '/api/v1/admin/access']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_reconcile_route_rejects_with_reason_and_preserves_admin_identity(self):
        self.login()
        body = dict(operation_id='reconcile-test-op', reason='reviewed', evidence_ref='test-evidence')
        result = dict(eligible=False, reason='WINDOW_USED_LEDGER_CONFLICT', preview=True, grant_id='test-grant')
        with patch('app.api.admin_console.reconcile', new=AsyncMock(return_value=result)) as reconcile:
            response = self.client.post(PATH + '/grants/test-grant/reconcile-close', json=body,
                                        headers={'x-admin-request':'1'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['data'], result)
        self.assertEqual(reconcile.call_args.args[0], 'test-grant')
        self.assertTrue(reconcile.call_args.args[1].preview)
        self.assertEqual(reconcile.call_args.args[2], 'local-admin:admin')


if __name__ == '__main__':
    unittest.main()
