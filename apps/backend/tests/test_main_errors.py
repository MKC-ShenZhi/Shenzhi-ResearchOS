import unittest
from unittest.mock import patch

from starlette.requests import Request

from app.core.errors import INTERNAL_ERROR_MESSAGE
from app.main import unexpected_error


class MainErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_error_is_safe_and_correlated(self):
        request = Request({
            'type': 'http', 'method': 'GET', 'path': '/test', 'headers': [],
            'query_string': b'', 'server': ('test', 80), 'scheme': 'http',
        })
        request.state.request_id = 'request-test-id'
        with patch('app.main.logger.exception') as logged:
            response = await unexpected_error(request, RuntimeError('database password must not leak'))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers['x-request-id'], 'request-test-id')
        self.assertIn(INTERNAL_ERROR_MESSAGE, response.body.decode())
        self.assertNotIn('database password', response.body.decode())
        logged.assert_called_once()
