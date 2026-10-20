"""Account-level topic follows; the JSON catalog stays the source of truth."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.interactions import TopicFollowRow
from app.schemas.interactions import TopicFollowItem, TopicFollowListResponse
from app.services.topics.registry import TopicRegistry, TopicRegistryError


class TopicFollowService:
    """Only enabled catalog topics can be followed; retries are idempotent."""

    def __init__(self, registry: TopicRegistry | None = None):
        self.registry = registry or TopicRegistry()

    async def follow(self, user_id: str, topic_id: str) -> int:
        require_followable_topic(self.registry, topic_id)
        async with session_scope() as session:
            await session.execute(
                insert(TopicFollowRow)
                .values(user_id=user_id, topic_id=topic_id)
                .on_conflict_do_nothing(index_elements=['user_id', 'topic_id'])
            )
            return await self._count(session, topic_id)

    async def unfollow(self, user_id: str, topic_id: str) -> int:
        # Unfollowing is idempotent and does not validate the catalog, so a topic
        # removed from the catalog can always be released.
        async with session_scope() as session:
            await session.execute(delete(TopicFollowRow).where(
                TopicFollowRow.user_id == user_id,
                TopicFollowRow.topic_id == topic_id,
            ))
            return await self._count(session, topic_id)

    async def follower_counts(self, topic_ids: list[str]) -> dict[str, int]:
        ids = list(dict.fromkeys(topic_ids))
        if not ids:
            return {}
        async with session_scope() as session:
            rows = await session.execute(
                select(TopicFollowRow.topic_id, func.count(func.distinct(TopicFollowRow.user_id)))
                .where(TopicFollowRow.topic_id.in_(ids))
                .group_by(TopicFollowRow.topic_id)
            )
            return {topic_id: int(total) for topic_id, total in rows}

    async def followed_topic_ids(self, user_id: str, topic_ids: list[str]) -> set[str]:
        ids = list(dict.fromkeys(topic_ids))
        if not ids:
            return set()
        async with session_scope() as session:
            return set(await session.scalars(
                select(TopicFollowRow.topic_id).where(
                    TopicFollowRow.user_id == user_id,
                    TopicFollowRow.topic_id.in_(ids),
                )
            ))

    async def list_follows(self, user_id: str) -> TopicFollowListResponse:
        async with session_scope() as session:
            rows = list(await session.scalars(
                select(TopicFollowRow)
                .where(TopicFollowRow.user_id == user_id)
                .order_by(TopicFollowRow.created_at.desc(), TopicFollowRow.topic_id)
            ))
        return TopicFollowListResponse(
            items=[TopicFollowItem(topic_id=row.topic_id, followed_at=row.created_at) for row in rows],
            total=len(rows),
        )

    @staticmethod
    async def _count(session: AsyncSession, topic_id: str) -> int:
        return int(await session.scalar(
            select(func.count(func.distinct(TopicFollowRow.user_id))).where(TopicFollowRow.topic_id == topic_id)
        ) or 0)


def require_followable_topic(registry: TopicRegistry, topic_id: str) -> None:
    """Raise the stable 404 contract when the catalog cannot serve this topic."""
    try:
        registry.get_topic(topic_id)
    except TopicRegistryError as error:
        raise BusinessError(40401, '未找到对应主题', 404) from error
