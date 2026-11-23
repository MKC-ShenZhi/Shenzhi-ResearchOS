"""Real local HTTP regression: an Internet proxy cannot intercept Agent calls."""
import asyncio
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest
from unittest.mock import patch

from app.services.agent_gateway.client import AgentGateway


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
