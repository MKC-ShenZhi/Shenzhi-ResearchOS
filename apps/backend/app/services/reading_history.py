"""Persistence and Knowledge enrichment for paper reading history."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.models.reading_history import ReadingHistoryRow
from app.schemas.history import ReadingHistoryItem, ReadingHistoryResponse
from app.services.knowledge import KnowledgeService

MAX_HISTORY_SCAN = 100

class ReadingHistoryService:
    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def record(self, user_id: str, paper_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            statement = insert(ReadingHistoryRow).values(
                user_id=user_id, paper_id=paper_id, last_viewed_at=now,
            )
            await session.execute(statement.on_conflict_do_update(
                index_elements=['user_id', 'paper_id'],
                set_={'last_viewed_at': now},
            ))

    async def list(self, user_id: str, page: int, page_size: int, query: str) -> ReadingHistoryResponse:
        async with session_scope() as session:
            rows = list(await session.scalars(
                select(ReadingHistoryRow)
                .where(ReadingHistoryRow.user_id == user_id)
                .order_by(ReadingHistoryRow.last_viewed_at.desc(), ReadingHistoryRow.id.desc())
                .limit(MAX_HISTORY_SCAN)
            ))

        normalized_query = query.strip().casefold()
        candidate_rows = rows
        if not normalized_query:
            start = (page - 1) * page_size
            candidate_rows = rows[start:start + page_size]

        papers = await self.knowledge.batch_get_papers([row.paper_id for row in candidate_rows])
        papers_by_id = {paper.id: paper for paper in papers}
        enriched: list[ReadingHistoryItem] = []
        for row in candidate_rows:
            paper = papers_by_id.get(row.paper_id)
            if paper is None:
                continue
            haystack = ' '.join([
                paper.title,
                *paper.authors,
                paper.venue or '',
            ]).casefold()
            if normalized_query and normalized_query not in haystack:
                continue
            enriched.append(ReadingHistoryItem.model_validate({
                **paper.model_dump(),
                'paper_id': row.paper_id,
                'last_viewed_at': row.last_viewed_at,
            }))

        total = len(enriched)
        if normalized_query:
            start = (page - 1) * page_size
            enriched = enriched[start:start + page_size]
        else:
            # Without a search, only the requested page is enriched. The total
            # therefore represents the bounded history window, not just that page.
            total = len(rows)
        return ReadingHistoryResponse(
            items=enriched,
            total=total,
            page=page,
            page_size=page_size,
        )
