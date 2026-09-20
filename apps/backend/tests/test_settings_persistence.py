import os
import unittest
from uuid import uuid4

from app.core.database import dispose_engine
from app.services.user.settings import SettingsService
from app.schemas.settings import NotificationPreferences, UserSettingsPatch


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class SettingsPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await dispose_engine()
        self.service = SettingsService()
        suffix = uuid4().hex
        self.user_a = f'settings-test-user-a-{suffix}'
        self.user_b = f'settings-test-user-b-{suffix}'

    async def asyncTearDown(self):
        await dispose_engine()

    async def test_defaults_partial_updates_and_account_isolation(self):
        first = await self.service.get(self.user_a)
        self.assertEqual((first.locale, first.theme_mode), ('zh-CN', 'system'))
        updated = await self.service.patch(
            self.user_a,
            UserSettingsPatch(
                locale='en',
                notifications=NotificationPreferences(system=False),
            ),
        )
        other = await self.service.get(self.user_b)
        self.assertEqual(updated.locale, 'en')
        self.assertFalse(updated.notifications.system)
        self.assertEqual(other.locale, 'zh-CN')
        self.assertTrue(other.notifications.system)
