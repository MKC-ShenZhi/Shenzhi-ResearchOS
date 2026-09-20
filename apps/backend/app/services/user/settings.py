"""Authenticated user settings persistence."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import get_session_factory, session_scope
from app.models.settings import UserSettingsRow
from app.schemas.settings import (
    NotificationPreferences,
    UserSettingsPatch,
    UserSettingsResponse,
)


def _response(row: UserSettingsRow) -> UserSettingsResponse:
    return UserSettingsResponse(
        locale=row.locale,
        theme_mode=row.theme_mode,
        notifications=NotificationPreferences(
            activity=row.notify_activity,
            subscription=row.notify_subscription,
            interaction=row.notify_interaction,
            system=row.notify_system,
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SettingsService:
    async def get(self, user_id: str) -> UserSettingsResponse:
        async with session_scope() as db:
            await db.execute(
                insert(UserSettingsRow)
                .values(user_id=user_id)
                .on_conflict_do_nothing(index_elements=[UserSettingsRow.user_id])
            )
        async with get_session_factory()() as db:
            row = await db.scalar(
                select(UserSettingsRow).where(UserSettingsRow.user_id == user_id)
            )
        assert row is not None
        return _response(row)

    async def patch(
        self, user_id: str, patch: UserSettingsPatch,
    ) -> UserSettingsResponse:
        values: dict[str, object] = {}
        fields = patch.model_fields_set
        if 'locale' in fields and patch.locale is not None:
            values['locale'] = patch.locale
        if 'theme_mode' in fields and patch.theme_mode is not None:
            values['theme_mode'] = patch.theme_mode
        if 'notifications' in fields and patch.notifications is not None:
            values.update({
                'notify_activity': patch.notifications.activity,
                'notify_subscription': patch.notifications.subscription,
                'notify_interaction': patch.notifications.interaction,
                'notify_system': patch.notifications.system,
            })

        statement = insert(UserSettingsRow).values(user_id=user_id, **values)
        if values:
            statement = statement.on_conflict_do_update(
                index_elements=[UserSettingsRow.user_id],
                set_={**values, 'updated_at': statement.excluded.updated_at},
            )
        else:
            statement = statement.on_conflict_do_nothing(
                index_elements=[UserSettingsRow.user_id],
            )
        async with session_scope() as db:
            await db.execute(statement)
        return await self.get(user_id)
