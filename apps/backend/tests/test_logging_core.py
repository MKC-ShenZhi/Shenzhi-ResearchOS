import json
import logging
import unittest
from starlette.requests import Request

import httpx

from app.api.knowledge import request_id, unknown_error
from app.core.logging import JsonFormatter, log_event
from app.core.request_context import get_request_id, reset_request_id, set_request_id
from app.main import app


class JsonCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(json.loads(JsonFormatter().format(record)))


class LoggingCoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.capture = JsonCapture()
        self.app_logger = logging.getLogger('app')
        self.app_logger.addHandler(self.capture)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url='http://test',
        )

    async def asyncTearDown(self):
        self.app_logger.removeHandler(self.capture)
        await self.client.aclose()

    async def request_context_response(self):
        return {'request_id': get_request_id()}

    async def test_missing_request_id_is_generated_and_context_is_cleared(self):
        path = '/__logging_test__/context'
        app.add_api_route(path, self.request_context_response, methods=['GET'])
        try:
            response = await self.client.get(path)
        finally:
            route = next(route for route in app.router.routes if getattr(route, 'path', None) == path)
            app.router.routes.remove(route)
        request_id = response.headers['x-request-id']
        self.assertRegex(request_id, r'^[0-9a-f-]{36}$')
        self.assertEqual(response.json()['request_id'], request_id)
        self.assertIsNone(get_request_id())

    async def test_valid_request_id_is_reused_and_http_log_is_structured(self):
        path = '/__logging_test__/context'
        app.add_api_route(path, self.request_context_response, methods=['GET'])
        try:
            response = await self.client.get(path, headers={'X-Request-ID': 'backend-test-1'})
        finally:
            route = next(route for route in app.router.routes if getattr(route, 'path', None) == path)
            app.router.routes.remove(route)
        self.assertEqual(response.headers['x-request-id'], 'backend-test-1')
        completed = [item for item in self.capture.records if item.get('event') == 'http.request.completed']
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]['request_id'], 'backend-test-1')
        self.assertEqual(completed[0]['method'], 'GET')
        self.assertEqual(completed[0]['route'], '/__logging_test__/context')
        self.assertEqual(completed[0]['status_code'], 200)
        self.assertIsInstance(completed[0]['duration_ms'], int)

    async def test_invalid_request_id_is_replaced(self):
        path = '/__logging_test__/context'
        app.add_api_route(path, self.request_context_response, methods=['GET'])
        try:
            response = await self.client.get(path, headers={'X-Request-ID': 'invalid request id'})
        finally:
            route = next(route for route in app.router.routes if getattr(route, 'path', None) == path)
            app.router.routes.remove(route)
        request_id = response.headers['x-request-id']
        self.assertNotEqual(request_id, 'invalid request id')
        self.assertRegex(request_id, r'^[0-9a-f-]{36}$')
        self.assertEqual(response.json()['request_id'], request_id)

    async def test_backend_logger_uses_an_explicit_field_allowlist(self):
        log_event(
            self.app_logger,
            logging.INFO,
            'test.allowlist',
            {
                'request_id': 'allowlist-test-1',
                'route': '/health',
                'authorization': 'must-not-be-logged',
            },
        )
        record = next(item for item in self.capture.records if item.get('event') == 'test.allowlist')
        self.assertEqual(record['request_id'], 'allowlist-test-1')
        self.assertEqual(record['route'], '/health')
        self.assertNotIn('authorization', record)

    async def test_unknown_exception_has_one_traceback_and_safe_response(self):
        path = '/__logging_test__/boom'

        async def boom():
            raise RuntimeError('database password must not leak')

        app.add_api_route(path, boom, methods=['GET'])
        try:
            response = await self.client.get(path, headers={'X-Request-ID': 'backend-error-1'})
        finally:
            route = next(route for route in app.router.routes if getattr(route, 'path', None) == path)
            app.router.routes.remove(route)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers['x-request-id'], 'backend-error-1')
        self.assertNotIn('database password', response.text)
        errors = [item for item in self.capture.records if item.get('event') == 'exception.unexpected']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['request_id'], 'backend-error-1')
        self.assertEqual(errors[0]['error_type'], 'RuntimeError')
        self.assertIn('RuntimeError', errors[0]['traceback'])
        self.assertEqual(sum('traceback' in item for item in self.capture.records), 1)
        self.assertIsNone(get_request_id())

    async def test_knowledge_catch_all_logs_once_without_changing_response(self):
        request = Request({
            'type': 'http', 'method': 'POST', 'path': '/api/v1/knowledge/search',
            'headers': [(b'x-request-id', b'knowledge-error-1')],
            'query_string': b'', 'server': ('test', 80), 'scheme': 'http',
        })
        token = set_request_id('knowledge-error-1')
        try:
            try:
                raise RuntimeError('upstream contract failure')
            except Exception as error:
                response = unknown_error(request, error)
        finally:
            reset_request_id(token)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(json.loads(response.body), {
            'code': 'UNKNOWN',
            'message': '知识服务请求失败',
            'retryable': False,
            'requestId': 'knowledge-error-1',
        })
        errors = [item for item in self.capture.records if item.get('event') == 'exception.unexpected']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['request_id'], 'knowledge-error-1')
        self.assertEqual(errors[0]['error_type'], 'RuntimeError')
        self.assertEqual(errors[0]['error_code'], 'UNKNOWN')
        self.assertIn('RuntimeError', errors[0]['traceback'])

    async def test_knowledge_error_request_id_prefers_context(self):
        request = Request({
            'type': 'http', 'method': 'POST', 'path': '/api/v1/knowledge/search',
            'headers': [(b'x-request-id', b'header-request-id')],
            'query_string': b'', 'server': ('test', 80), 'scheme': 'http',
        })
        token = set_request_id('context-request-id')
        try:
            self.assertEqual(request_id(request), 'context-request-id')
        finally:
            reset_request_id(token)


if __name__ == '__main__':
    unittest.main()
