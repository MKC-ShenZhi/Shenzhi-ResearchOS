"""Authenticated personal profile persistence."""

from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import get_session_factory, session_scope
from app.models.profile import UserProfileRow
from app.schemas.profile import UserProfilePatch, UserProfileResponse

AVATAR_KEYS = tuple(f'avatar-{index:02d}' for index in range(1, 6))


def default_avatar_key(user_id: str) -> str:
    """Choose a stable default while still persisting the chosen key."""
    digest = sha256(user_id.encode('utf-8')).digest()
    return AVATAR_KEYS[int.from_bytes(digest[:4], 'big') % len(AVATAR_KEYS)]


def _response(row: UserProfileRow) -> UserProfileResponse:
    return UserProfileResponse.model_validate(row)


class ProfileService:
    async def get(self, user_id: str) -> UserProfileResponse:
        async with session_scope() as db:
            await db.execute(
                insert(UserProfileRow)
                .values(user_id=user_id, avatar_key=default_avatar_key(user_id))
                .on_conflict_do_nothing(index_elements=[UserProfileRow.user_id])
            )
        async with get_session_factory()() as db:
            row = await db.scalar(
                select(UserProfileRow).where(UserProfileRow.user_id == user_id)
            )
        assert row is not None
        return _response(row)

    async def patch(self, user_id: str, patch: UserProfilePatch) -> UserProfileResponse:
        values: dict[str, object] = {}
        for field in ('bio', 'achievements', 'educations', 'biography', 'institutions'):
            if field in patch.model_fields_set:
                value = getattr(patch, field)
                if value is not None:
                    values[field] = (
                        [item.model_dump(mode='json') for item in value]
                        if isinstance(value, list) else value
                    )
        if 'avatar_key' in patch.model_fields_set and patch.avatar_key is not None:
            values['avatar_key'] = patch.avatar_key
            values['avatar_selected'] = True

        await self.get(user_id)
        if values:
            values['updated_at'] = datetime.now(timezone.utc)
            async with session_scope() as db:
                row = await db.scalar(
                    select(UserProfileRow)
                    .where(UserProfileRow.user_id == user_id)
                    .with_for_update()
                )
                assert row is not None
                for field, value in values.items():
                    setattr(row, field, value)
        return await self.get(user_id)
