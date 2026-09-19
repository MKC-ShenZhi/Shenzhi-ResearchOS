"""Idempotent removal of every currently persisted business record for one user."""

from dataclasses import dataclass

from sqlalchemy import delete, select

from app.core.database import session_scope
from app.models.chat import ChatSessionRow
from app.models.collections import CollectionFolderRow, CollectionItemRow, CollectionUserStateRow
from app.models.profile import UserProfileRow
from app.models.reading_history import ReadingHistoryRow
from app.models.settings import UserSettingsRow
from app.services.sessions import repository


@dataclass(frozen=True)
class BusinessDataDeletionResult:
    profiles_deleted: int
    settings_deleted: int
    chat_sessions_deleted: int


class AccountDeletionService:
    """Remove business data before the separate Better Auth account is deleted.

    All current business tables share CHAT_DATABASE_URL, so this method has one
    transaction. Repeating it is safe: a completed deletion simply returns
    zero counts, allowing a user to retry if the later auth deletion fails.
    """

    async def delete_all_for_user(self, user_id: str) -> BusinessDataDeletionResult:
        owner = f'user:{user_id}'
        async with session_scope() as db:
            session_ids = {
                str(session_id)
                for session_id in (
                    await db.scalars(
                        select(ChatSessionRow.id)
                        .where(ChatSessionRow.owner == owner)
                    )
                ).all()
            }
            # Stop current-worker generators before deleting their durable rows.
            # A multi-worker deployment still needs distributed cancellation.
            await repository.purge_owner_runtime(owner, session_ids)
            folder_ids = select(CollectionFolderRow.id).where(CollectionFolderRow.user_id == user_id)
            await db.execute(delete(CollectionItemRow).where(CollectionItemRow.folder_id.in_(folder_ids)))
            await db.execute(delete(CollectionFolderRow).where(CollectionFolderRow.user_id == user_id))
            await db.execute(delete(CollectionUserStateRow).where(CollectionUserStateRow.user_id == user_id))
            await db.execute(delete(ReadingHistoryRow).where(ReadingHistoryRow.user_id == user_id))
            profiles = await db.execute(
                delete(UserProfileRow)
                .where(UserProfileRow.user_id == user_id)
                .returning(UserProfileRow.user_id)
            )
            settings = await db.execute(
                delete(UserSettingsRow)
                .where(UserSettingsRow.user_id == user_id)
                .returning(UserSettingsRow.user_id)
            )
            sessions = await db.execute(
                delete(ChatSessionRow)
                .where(ChatSessionRow.owner == owner)
                .returning(ChatSessionRow.id)
            )

        # chat_messages cascade from chat_sessions. Counts deliberately omit
        # message content and identifiers so logs and the response stay safe.
        return BusinessDataDeletionResult(
            profiles_deleted=len(profiles.all()),
            settings_deleted=len(settings.all()),
            chat_sessions_deleted=len(sessions.all()),
        )
