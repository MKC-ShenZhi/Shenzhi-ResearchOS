"""Persistence and Knowledge enrichment for paper reading history."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.models.reading_history import ReadingHistoryRow
from app.schemas.history import ReadingHistoryItem, ReadingHistoryResponse
from app.services.knowledge.service import KnowledgeService
from app.services.recommendation.behavior import BehaviorEventService

MAX_HISTORY_SCAN = 100

class ReadingHistoryService:
    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def record(self, user_id: str, paper_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            previous_view = await session.scalar(select(ReadingHistoryRow.last_viewed_at).where(
                ReadingHistoryRow.user_id == user_id,
                ReadingHistoryRow.paper_id == paper_id,
            ))
            statement = insert(ReadingHistoryRow).values(
                user_id=user_id, paper_id=paper_id, last_viewed_at=now,
            )
            await session.execute(statement.on_conflict_do_update(
                index_elements=['user_id', 'paper_id'],
                set_={'last_viewed_at': now},
            ))
            if previous_view is None or (now - previous_view).total_seconds() >= 600:
                await BehaviorEventService().record_explicit(
                    session, user_id=user_id, event_type='paper_detail_view',
                    entity_type='paper', entity_id=paper_id, source='paper_detail',
                )

    async def mark_read(self, user_id: str, paper_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            statement = insert(ReadingHistoryRow).values(
                user_id=user_id, paper_id=paper_id, last_viewed_at=now, read_at=now,
            )
            first_read = await session.scalar(statement.on_conflict_do_update(
                index_elements=['user_id', 'paper_id'],
                set_={'read_at': now},
                where=ReadingHistoryRow.read_at.is_(None),
            ).returning(ReadingHistoryRow.id))
            if first_read is not None:
                await BehaviorEventService().record_explicit(
                    session, user_id=user_id, event_type='paper_read',
                    entity_type='paper', entity_id=paper_id,
                )

    async def paper_status_ids(self, user_id: str, paper_ids: list[str]) -> tuple[list[str], list[str]]:
        async with session_scope() as session:
            rows = (await session.execute(
                select(ReadingHistoryRow.paper_id, ReadingHistoryRow.read_at).where(
                    ReadingHistoryRow.user_id == user_id,
                    ReadingHistoryRow.paper_id.in_(paper_ids),
                )
            )).all()
            found = {paper_id: read_at for paper_id, read_at in rows}
        return (
            [paper_id for paper_id in paper_ids if paper_id in found and found[paper_id] is not None],
            [paper_id for paper_id in paper_ids if paper_id in found and found[paper_id] is None],
        )

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
