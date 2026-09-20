"""Live PostgreSQL acceptance for complete, isolated, idempotent account cleanup."""

import os
import unittest
import uuid
from sqlalchemy import select

from app.core.database import session_scope
from app.models.chat import ChatMessageRow, ChatSessionRow
from app.models.collections import CollectionFolderRow, CollectionItemRow, CollectionUserStateRow
from app.models.profile import UserProfileRow
from app.models.reading_history import ReadingHistoryRow
from app.models.settings import UserSettingsRow
from app.services.user.account_deletion import AccountDeletionService


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class AccountDeletionPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_deletes_all_target_data_preserves_other_user_and_is_idempotent(self):
        target_user = f'delete-test-{uuid.uuid4()}'
        other_user = f'keep-test-{uuid.uuid4()}'
        target_session_id = uuid.uuid4()
        other_session_id = uuid.uuid4()
        target_message_id = uuid.uuid4()
        other_message_id = uuid.uuid4()

        async with session_scope() as db:
            db.add_all([
                UserProfileRow(user_id=target_user, avatar_key='avatar-01'),
                UserProfileRow(user_id=other_user, avatar_key='avatar-01'),
                UserSettingsRow(user_id=target_user),
                UserSettingsRow(user_id=other_user),
                CollectionUserStateRow(user_id=target_user),
                CollectionUserStateRow(user_id=other_user),
                ReadingHistoryRow(user_id=target_user, paper_id='paper-a'),
                ReadingHistoryRow(user_id=other_user, paper_id='paper-b'),
                ChatSessionRow(id=target_session_id, owner=f'user:{target_user}', title='delete', settings={}),
                ChatSessionRow(id=other_session_id, owner=f'user:{other_user}', title='keep', settings={}),
                ChatMessageRow(
                    id=target_message_id, session_id=target_session_id, question='delete', settings={},
                    attachment_context='', warnings=[], content='', reasoning='', status='done',
                    message_refs=[], followups=[], duration_ms=0,
                ),
                ChatMessageRow(
                    id=other_message_id, session_id=other_session_id, question='keep', settings={},
                    attachment_context='', warnings=[], content='', reasoning='', status='done',
                    message_refs=[], followups=[], duration_ms=0,
                ),
            ])
            target_folder = CollectionFolderRow(user_id=target_user, name='target')
            other_folder = CollectionFolderRow(user_id=other_user, name='other')
            db.add_all([target_folder, other_folder])
            await db.flush()
            db.add_all([
                CollectionItemRow(folder_id=target_folder.id, paper_id='paper-a'),
                CollectionItemRow(folder_id=other_folder.id, paper_id='paper-b'),
            ])

        target_folder_id = target_folder.id
        other_folder_id = other_folder.id

        try:
            result = await AccountDeletionService().delete_all_for_user(target_user)
            self.assertEqual((result.profiles_deleted, result.settings_deleted, result.chat_sessions_deleted), (1, 1, 1))

            async with session_scope() as db:
                self.assertIsNone(await db.get(UserProfileRow, target_user))
                self.assertIsNone(await db.get(UserSettingsRow, target_user))
                self.assertIsNone(await db.get(ChatSessionRow, target_session_id))
                self.assertIsNone(await db.get(ChatMessageRow, target_message_id))
                self.assertIsNone(await db.get(CollectionUserStateRow, target_user))
                self.assertIsNone(await db.get(CollectionFolderRow, target_folder_id))
                self.assertEqual(len((await db.scalars(select(CollectionItemRow).where(CollectionItemRow.folder_id == target_folder_id))).all()), 0)
                self.assertIsNotNone(await db.get(CollectionUserStateRow, other_user))
                self.assertIsNotNone(await db.get(CollectionFolderRow, other_folder_id))
                self.assertEqual(len((await db.scalars(select(ReadingHistoryRow).where(ReadingHistoryRow.user_id == target_user))).all()), 0)
                self.assertEqual(len((await db.scalars(select(ReadingHistoryRow).where(ReadingHistoryRow.user_id == other_user))).all()), 1)
                self.assertIsNotNone(await db.get(UserProfileRow, other_user))
                self.assertIsNotNone(await db.get(UserSettingsRow, other_user))
                self.assertIsNotNone(await db.get(ChatSessionRow, other_session_id))
                self.assertIsNotNone(await db.get(ChatMessageRow, other_message_id))

            repeated = await AccountDeletionService().delete_all_for_user(target_user)
            self.assertEqual((repeated.profiles_deleted, repeated.settings_deleted, repeated.chat_sessions_deleted), (0, 0, 0))
        finally:
            async with session_scope() as db:
                for model, key in (
                    (ChatMessageRow, target_message_id),
                    (ChatMessageRow, other_message_id),
                    (ChatSessionRow, target_session_id),
                    (ChatSessionRow, other_session_id),
                    (UserProfileRow, target_user),
                    (UserProfileRow, other_user),
                    (UserSettingsRow, target_user),
                    (UserSettingsRow, other_user),
                    (CollectionUserStateRow, other_user),
                    (CollectionFolderRow, other_folder_id),
                ):
                    row = await db.get(model, key)
                    if row is not None:
                        await db.delete(row)
                for row in (await db.scalars(select(ReadingHistoryRow).where(ReadingHistoryRow.user_id == other_user))).all():
                    await db.delete(row)


if __name__ == '__main__':
    unittest.main()
