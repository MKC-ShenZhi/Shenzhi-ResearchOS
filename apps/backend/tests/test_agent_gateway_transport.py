"""Real local HTTP regression: an Internet proxy cannot intercept Agent calls."""
import asyncio
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import AsyncMock, patch

from app.services.agent_gateway.client import AgentGateway
from app.services.agent_gateway.v2 import AgentGatewayV2
from app.core.errors import BusinessError


@asynccontextmanager
async def local_server(payload, status=200):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization')))
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            request_body = self.rfile.read(length) if length else b''
            requests.append((self.path, self.headers.get('Authorization'), request_body))
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', requests
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)


class AgentGatewayTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_recover_submission_allows_missing_only_for_session_recovery(self):
        gateway = AgentGatewayV2()
        with patch('app.services.agent_gateway.v2.session_scope') as scope:
            from unittest.mock import MagicMock
            db = MagicMock()
            db.scalar = AsyncMock(return_value=None)
            scope.return_value.__aenter__ = AsyncMock(return_value=db)
            scope.return_value.__aexit__ = AsyncMock(return_value=False)
            with self.assertRaises(BusinessError) as raised:
                await gateway.recover_submission('owner', 'missing-key')
            self.assertEqual(raised.exception.status, 404)
            self.assertIsNone(await gateway.recover_submission(
                'owner', 'missing-key', allow_missing=True))

    async def test_agent_config_bypasses_proxy_without_no_proxy_configuration(self):
        async with local_server({'models': [], 'default_model': None, 'skills': []}) as (origin, calls), \
                   local_server({'error': {'code': 20004, 'message': 'proxy must not receive service requests'}}, 502) as (proxy, proxy_calls):
            with patch.dict('os.environ', {
                'HTTP_PROXY': proxy, 'HTTPS_PROXY': proxy, 'ALL_PROXY': proxy,
                'http_proxy': proxy, 'https_proxy': proxy, 'all_proxy': proxy,
                'NO_PROXY': '', 'no_proxy': '',
            }):
                config = await AgentGateway(base_url=origin, token='test-only-service-token').config()
            self.assertEqual(config['models'], [])
            self.assertEqual(calls, [('/internal/v1/config', 'Bearer test-only-service-token')])
            self.assertEqual(proxy_calls, [])

    async def test_v2_execution_methods_use_v2_endpoints(self):
        payload = {
            'task_id': 'task-1', 'current_run_id': 'run-1', 'run_ids': ['run-1'],
            'events': [], 'report': None, 'cancel_requested': True, 'stored': True,
        }
        async with local_server(payload) as (origin, calls):
            gateway = AgentGatewayV2(base_url=origin, token='gateway-token')
            await gateway.task('task-1', 'anon:owner')
            await gateway.run('run-1', 'anon:owner')
            await gateway.task_runs('task-1', 'anon:owner')
            await gateway.events('run-1', 'anon:owner', 4)
            await gateway.cancel('task-1', 'anon:owner')
            await gateway.steer('run-1', 'anon:owner', 'continue')
        self.assertEqual([item[0].split('?')[0] for item in calls], [
            '/internal/v2/tasks/task-1', '/internal/v2/runs/run-1',
            '/internal/v2/tasks/task-1/runs', '/internal/v2/runs/run-1/events',
            '/internal/v2/tasks/task-1/cancel', '/internal/v2/runs/run-1/steer',
        ])
        self.assertTrue(all(item[1] == 'Bearer gateway-token' for item in calls))

    async def test_v2_gateway_delegates_shared_v1_files_with_service_credential(self):
        async with local_server({'content_base64': 'cmVwb3J0', 'media_type': 'text/markdown'}) as (origin, calls):
            with patch.dict('os.environ', {'AGENT_SERVICE_TOKEN': 'service-token'}):
                gateway = AgentGatewayV2(base_url=origin, token='gateway-token')
                content, media_type = await gateway.read_session_file(
                    'anon:owner', 'session-1', 'report.md')
        self.assertEqual((content, media_type), (b'report', 'text/markdown'))
        self.assertEqual(len(calls), 1)
        parsed = urlsplit(calls[0][0])
        self.assertEqual(parsed.path, '/internal/v1/sessions/session-1/files')
        self.assertEqual(parse_qs(parsed.query), {'owner_id': ['anon:owner'], 'path': ['report.md']})
        self.assertEqual(calls[0][1], 'Bearer service-token')
