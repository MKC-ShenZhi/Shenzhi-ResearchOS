"""Account-level paper likes with one unique row per (user, paper)."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.models.interactions import PaperLikeRow
from app.schemas.interactions import LikedPaperItem, LikedPaperListResponse
from app.services.knowledge.service import KnowledgeService


class PaperLikeService:
    """Likes are idempotent by unique key, so retries never inflate the count."""

    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def like(self, user_id: str, paper_id: str) -> int:
        async with session_scope() as session:
            await session.execute(
                insert(PaperLikeRow)
                .values(user_id=user_id, paper_id=paper_id)
                .on_conflict_do_nothing(index_elements=['user_id', 'paper_id'])
            )
            return await self._count(session, paper_id)

    async def unlike(self, user_id: str, paper_id: str) -> int:
        async with session_scope() as session:
            await session.execute(delete(PaperLikeRow).where(
                PaperLikeRow.user_id == user_id,
                PaperLikeRow.paper_id == paper_id,
            ))
            return await self._count(session, paper_id)

    async def like_counts(self, paper_ids: list[str]) -> dict[str, int]:
        """Distinct logged-in users per paper; repeated likes never count twice."""
        ids = list(dict.fromkeys(paper_ids))
        if not ids:
            return {}
        async with session_scope() as session:
            rows = await session.execute(
                select(PaperLikeRow.paper_id, func.count(func.distinct(PaperLikeRow.user_id)))
                .where(PaperLikeRow.paper_id.in_(ids))
                .group_by(PaperLikeRow.paper_id)
            )
            return {paper_id: int(total) for paper_id, total in rows}

    async def liked_paper_ids(self, user_id: str, paper_ids: list[str]) -> set[str]:
        ids = list(dict.fromkeys(paper_ids))
        if not ids:
            return set()
        async with session_scope() as session:
            return set(await session.scalars(
                select(PaperLikeRow.paper_id).where(
                    PaperLikeRow.user_id == user_id,
                    PaperLikeRow.paper_id.in_(ids),
                )
            ))

    async def liked_papers(self, user_id: str, page: int, page_size: int) -> LikedPaperListResponse:
        async with session_scope() as session:
            rows = list(await session.scalars(
                select(PaperLikeRow)
                .where(PaperLikeRow.user_id == user_id)
                .order_by(PaperLikeRow.created_at.desc(), PaperLikeRow.paper_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ))
            total = await session.scalar(
                select(func.count(PaperLikeRow.paper_id)).where(PaperLikeRow.user_id == user_id)
            )
        summaries = await self.knowledge.batch_get_papers([row.paper_id for row in rows])
        summaries_by_id = {paper.id: paper for paper in summaries}
        return LikedPaperListResponse(
            items=[
                LikedPaperItem.model_validate({
                    **self._paper_data(summaries_by_id.get(row.paper_id), row.paper_id),
                    'paper_id': row.paper_id,
                    'liked_at': row.created_at,
                })
                for row in rows
            ],
            total=total or 0,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def _count(session: AsyncSession, paper_id: str) -> int:
        return int(await session.scalar(
            select(func.count(func.distinct(PaperLikeRow.user_id))).where(PaperLikeRow.paper_id == paper_id)
        ) or 0)

    @staticmethod
    def _paper_data(summary, paper_id: str) -> dict:
        if summary is not None:
            return {**summary.model_dump(), 'is_available': True}
        return {
            'id': paper_id,
            'title': '论文暂不可用',
            'provenance': {'external_id': paper_id},
            'is_available': False,
        }
