import os
import unittest

from app.core.database import dispose_engine
from app.services.settings import SettingsService
from app.schemas.settings import NotificationPreferences, UserSettingsPatch


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class SettingsPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await dispose_engine()
        self.service = SettingsService()

    async def asyncTearDown(self):
        await dispose_engine()

    async def test_defaults_partial_updates_and_account_isolation(self):
        first = await self.service.get('settings-test-user-a')
        self.assertEqual((first.locale, first.theme_mode), ('zh-CN', 'system'))
        updated = await self.service.patch(
            'settings-test-user-a',
            UserSettingsPatch(
                locale='en',
                notifications=NotificationPreferences(system=False),
            ),
        )
        other = await self.service.get('settings-test-user-b')
        self.assertEqual(updated.locale, 'en')
        self.assertFalse(updated.notifications.system)
        self.assertEqual(other.locale, 'zh-CN')
        self.assertTrue(other.notifications.system)
