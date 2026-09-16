import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.profile import UserProfileResponse
from app.services.profile import AVATAR_KEYS, default_avatar_key


def profile_response() -> UserProfileResponse:
    now = datetime.now(timezone.utc)
    return UserProfileResponse(
        avatar_key='avatar-01',
        avatar_selected=False,
        bio='',
        achievements=[],
        educations=[],
        biography='',
        institutions=[],
        created_at=now,
        updated_at=now,
    )


class ProfileApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-user-id': 'profile-user-a',
        }

    def tearDown(self):
        self.env.stop()

    def test_get_uses_only_trusted_authenticated_identity(self):
        with patch('app.api.profile.service.get', new=AsyncMock(return_value=profile_response())) as get:
            response = self.client.get('/api/v1/profile', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['avatar_key'], 'avatar-01')
        get.assert_awaited_once_with('profile-user-a')

    def test_anonymous_cannot_read_or_patch_profile(self):
        anonymous = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }
        self.assertEqual(self.client.get('/api/v1/profile', headers=anonymous).status_code, 401)
        self.assertEqual(
            self.client.patch('/api/v1/profile', headers=anonymous, json={'bio': 'test'}).status_code,
            401,
        )

    def test_patch_rejects_identity_unknown_fields_and_invalid_content(self):
        invalid_payloads = [
            {'user_id': 'other-user'},
            {'avatar_key': 'avatar-99'},
            {'bio': 'x' * 501},
            {'achievements': [{'title': 'award', 'year': '20xx'}]},
            {'educations': [{'institution': 'school', 'unexpected': True}]},
            {'institutions': [{'name': ''}]},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.patch('/api/v1/profile', headers=self.headers, json=payload)
                self.assertEqual(response.status_code, 422)

    def test_patch_passes_whitelisted_structured_update(self):
        expected = profile_response().model_copy(update={'bio': '研究知识增强生成。'})
        with patch('app.api.profile.service.patch', new=AsyncMock(return_value=expected)) as update:
            response = self.client.patch(
                '/api/v1/profile', headers=self.headers,
                json={'bio': '研究知识增强生成。'},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['bio'], '研究知识增强生成。')
        self.assertEqual(update.await_args.args[0], 'profile-user-a')
        self.assertNotIn('user_id', update.await_args.args[1].model_fields_set)

    def test_default_avatar_is_stable_and_in_allowlist(self):
        self.assertEqual(default_avatar_key('same-user'), default_avatar_key('same-user'))
        self.assertIn(default_avatar_key('same-user'), AVATAR_KEYS)


if __name__ == '__main__':
    unittest.main()
