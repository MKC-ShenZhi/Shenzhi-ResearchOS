"""Persistence and Knowledge enrichment for paper reading history."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.core.database import session_scope
from app.models.reading_history import ReadingHistoryRow
from app.schemas.history import ReadingHistoryItem, ReadingHistoryResponse
from app.services.knowledge import KnowledgeService, KnowledgeServiceError


class ReadingHistoryService:
    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def record(self, user_id: str, paper_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = await session.scalar(
                select(ReadingHistoryRow).where(
                    ReadingHistoryRow.user_id == user_id,
                    ReadingHistoryRow.paper_id == paper_id,
                )
            )
            if row is None:
                session.add(ReadingHistoryRow(user_id=user_id, paper_id=paper_id, last_viewed_at=now))
            else:
                row.last_viewed_at = now

    async def list(self, user_id: str, page: int, page_size: int, query: str) -> ReadingHistoryResponse:
        async with session_scope() as session:
            rows = list(await session.scalars(
                select(ReadingHistoryRow)
                .where(ReadingHistoryRow.user_id == user_id)
                .order_by(ReadingHistoryRow.last_viewed_at.desc(), ReadingHistoryRow.id.desc())
            ))

        enriched: list[ReadingHistoryItem] = []
        for row in rows:
            try:
                paper = await self.knowledge.get_paper(row.paper_id)
            except KnowledgeServiceError as error:
                if error.status_code == 404 or error.error.code == 'NOT_FOUND':
                    continue
                raise
            haystack = ' '.join([
                paper.title,
                *paper.authors,
                paper.venue or '',
            ]).casefold()
            if query and query.casefold() not in haystack:
                continue
            enriched.append(ReadingHistoryItem.model_validate({
                **paper.model_dump(),
                'paper_id': row.paper_id,
                'last_viewed_at': row.last_viewed_at,
            }))

        start = (page - 1) * page_size
        return ReadingHistoryResponse(
            items=enriched[start:start + page_size],
            total=len(enriched),
            page=page,
            page_size=page_size,
        )