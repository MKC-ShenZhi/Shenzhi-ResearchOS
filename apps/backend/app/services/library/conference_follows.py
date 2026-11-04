"""Account-level conference deadline follows; the deadline snapshot stays the source of truth."""

from __future__ import annotations

from sqlalchemy import delete, select, func
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.models.interactions import ConferenceFollowRow
from app.models.conference_snapshot import ConferenceSnapshotRow
from app.services.conferences import ConferenceNotFoundError, load_conference_catalog
from app.services.conferences_repository import PUBLISH_LOCK_KEY


class ConferenceFollowService:
    """Retries are idempotent; callers validate the id against the snapshot before following."""

    async def follow(self, user_id: str, conference_id: str) -> None:
        async with session_scope() as session:
            await session.execute(
                select(func.pg_advisory_xact_lock_shared(PUBLISH_LOCK_KEY))
            )
            # Cached API catalogs can lag by five minutes. Validate against the
            # current DB version while publication is excluded, then insert.
            exists = await session.scalar(
                select(
                    ConferenceSnapshotRow.payload["conferences"].contains(
                        [{"id": conference_id}]
                    )
                ).where(ConferenceSnapshotRow.id == 1)
            )
            if exists is None:
                exists = any(
                    record.conference.id == conference_id
                    for record in load_conference_catalog().records
                )
            if not exists:
                raise ConferenceNotFoundError(conference_id)
            await session.execute(
                insert(ConferenceFollowRow)
                .values(user_id=user_id, conference_id=conference_id)
                .on_conflict_do_nothing(index_elements=["user_id", "conference_id"])
            )

    async def unfollow(self, user_id: str, conference_id: str) -> None:
        # No snapshot check, so a conference dropped from the snapshot can always be released.
        async with session_scope() as session:
            await session.execute(
                delete(ConferenceFollowRow).where(
                    ConferenceFollowRow.user_id == user_id,
                    ConferenceFollowRow.conference_id == conference_id,
                )
            )

    async def followed_ids(self, user_id: str) -> frozenset[str]:
        async with session_scope() as session:
            return frozenset(
                await session.scalars(
                    select(ConferenceFollowRow.conference_id).where(
                        ConferenceFollowRow.user_id == user_id
                    )
                )
            )
