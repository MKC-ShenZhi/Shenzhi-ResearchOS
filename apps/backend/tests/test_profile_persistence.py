import asyncio
import os
import unittest
from uuid import uuid4

from app.core.database import dispose_engine
from app.schemas.profile import (
    Achievement,
    EducationExperience,
    InstitutionExperience,
    UserProfilePatch,
)
from app.services.user.profile import ProfileService


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class ProfilePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await dispose_engine()
        self.service = ProfileService()
        suffix = uuid4().hex
        self.user_a = f'profile-test-a-{suffix}'
        self.user_b = f'profile-test-b-{suffix}'

    async def asyncTearDown(self):
        await dispose_engine()

    async def test_concurrent_creation_updates_and_account_isolation(self):
        first, second = await asyncio.gather(
            self.service.get(self.user_a),
            self.service.get(self.user_a),
        )
        self.assertEqual(first.avatar_key, second.avatar_key)
        self.assertFalse(first.avatar_selected)

        updated = await self.service.patch(
            self.user_a,
            UserProfilePatch(
                avatar_key='avatar-05',
                bio='研究可信人工智能。',
                achievements=[Achievement(title='最佳论文', year='2025')],
                educations=[EducationExperience(institution='示例大学', degree='博士')],
                biography='专注于可信人工智能与知识增强研究。',
                institutions=[InstitutionExperience(name='示例研究院', role='研究员')],
            ),
        )
        other = await self.service.get(self.user_b)
        self.assertEqual(updated.avatar_key, 'avatar-05')
        self.assertTrue(updated.avatar_selected)
        self.assertEqual(updated.bio, '研究可信人工智能。')
        self.assertEqual(updated.achievements[0].title, '最佳论文')
        self.assertEqual(other.bio, '')
        self.assertFalse(other.avatar_selected)


if __name__ == '__main__':
    unittest.main()
