import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.settings import NotificationPreferences, UserSettingsResponse


def settings_response(locale: str = 'zh-CN') -> UserSettingsResponse:
    now = datetime.now(timezone.utc)
    return UserSettingsResponse(
        locale=locale,
        theme_mode='system',
        notifications=NotificationPreferences(),
        created_at=now,
        updated_at=now,
    )


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-user-id': 'user-a',
        }

    def tearDown(self):
        self.env.stop()

    def test_get_uses_only_trusted_authenticated_identity(self):
        with patch('app.api.settings.service.get', new=AsyncMock(return_value=settings_response())) as get:
            response = self.client.get('/api/v1/settings', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['locale'], 'zh-CN')
        get.assert_awaited_once_with('user-a')

    def test_anonymous_cannot_read_or_patch_settings(self):
        anonymous = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }
        self.assertEqual(self.client.get('/api/v1/settings', headers=anonymous).status_code, 401)
        self.assertEqual(
            self.client.patch('/api/v1/settings', headers=anonymous, json={'locale': 'en'}).status_code,
            401,
        )

    def test_patch_rejects_unknown_or_invalid_fields(self):
        invalid_payloads = [
            {'user_id': 'other-user'},
            {'locale': 'fr'},
            {'theme_mode': 'sepia'},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.patch('/api/v1/settings', headers=self.headers, json=payload)
                self.assertEqual(response.status_code, 422)

    def test_patch_passes_whitelisted_partial_update(self):
        expected = settings_response('en')
        with patch('app.api.settings.service.patch', new=AsyncMock(return_value=expected)) as update:
            response = self.client.patch(
                '/api/v1/settings', headers=self.headers, json={'locale': 'en'},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['locale'], 'en')
        self.assertEqual(update.await_args.args[0], 'user-a')
        self.assertEqual(update.await_args.args[1].locale, 'en')


if __name__ == '__main__':
    unittest.main()
