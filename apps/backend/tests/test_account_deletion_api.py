import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.account_deletion import BusinessDataDeletionResult


class AccountDeletionApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-user-id': 'delete-user-a',
            'x-shenzhi-account-deletion': '1',
        }

    def tearDown(self):
        self.env.stop()

    def test_cleanup_uses_only_the_trusted_authenticated_user(self):
        result = BusinessDataDeletionResult(1, 1, 2)
        with patch(
            'app.api.account_deletion.service.delete_all_for_user',
            new=AsyncMock(return_value=result),
        ) as cleanup:
            response = self.client.post('/api/v1/account-deletion/cleanup', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['chat_sessions_deleted'], 2)
        cleanup.assert_awaited_once_with('delete-user-a')

    def test_cleanup_rejects_anonymous_or_a_missing_internal_marker(self):
        anonymous = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
            'x-shenzhi-account-deletion': '1',
        }
        self.assertEqual(
            self.client.post('/api/v1/account-deletion/cleanup', headers=anonymous).status_code,
            401,
        )
        headers = dict(self.headers)
        headers.pop('x-shenzhi-account-deletion')
        self.assertEqual(
            self.client.post('/api/v1/account-deletion/cleanup', headers=headers).status_code,
            403,
        )


if __name__ == '__main__':
    unittest.main()
