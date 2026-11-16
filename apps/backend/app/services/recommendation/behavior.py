"""Append-only, idempotent user behavior facts."""

from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.core.time import utc_now
from app.models.recommendation import BehaviorEventRow, RecommendationSnapshotRow
from app.schemas.behavior import BehaviorBatchRequest


class BehaviorEventService:
    async def record_explicit(
        self, session: AsyncSession, *, user_id: str, event_type: str,
        entity_type: str, entity_id: str, source: str = 'explicit',
    ) -> None:
        session.add(BehaviorEventRow(
            event_id=uuid4(), user_id=user_id, event_type=event_type,
            entity_type=entity_type, entity_id=entity_id, source=source,
        ))

    async def record_batch(self, user_id: str, body: BehaviorBatchRequest) -> int:
        # Keep a short per-account ingestion budget. This is noise control, not
        # a global abuse gateway; duplicate UUIDs remain harmless on retry.
        async with session_scope() as session:
            # Serialize concurrent batches for this account so each count sees
            # earlier committed writes before admitting another batch.
            await session.execute(select(func.pg_advisory_xact_lock(
                func.hashtext('behavior_events'), func.hashtext(user_id),
            )))
            recent = await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == user_id,
                BehaviorEventRow.received_at >= utc_now() - timedelta(minutes=1),
            ))
            if (recent or 0) + len(body.events) > 120:
                raise BusinessError(42901, '行为上报过于频繁', 429)
            await session.execute(delete(BehaviorEventRow).where(
                BehaviorEventRow.user_id == user_id,
                BehaviorEventRow.received_at < utc_now() - timedelta(days=90),
            ))
            inserted = 0
            for event in body.events:
                if event.event_type.startswith('recommendation_'):
                    snapshot = await session.get(RecommendationSnapshotRow, UUID(event.request_id or ''))
                    if (snapshot is None or snapshot.user_id != user_id
                        or snapshot.expires_at <= utc_now()
                        or not any(item['id'] == event.paper_id and item['rank'] == event.rank
                                   for item in snapshot.items)):
                        raise BusinessError(40001, '推荐事件与请求不匹配', 400)
                result = await session.execute(
                    insert(BehaviorEventRow).values(
                        event_id=event.event_id, user_id=user_id,
                        event_type=event.event_type,
                        entity_type='query' if event.event_type == 'search_submit' else 'paper',
                        entity_id=event.query if event.event_type == 'search_submit' else event.paper_id,
                        source=event.source,
                        request_id=event.request_id, rank=event.rank,
                        query_id=event.query_id or (event.event_id if event.event_type == 'search_submit' else None),
                        duration_seconds=event.duration_seconds,
                    ).on_conflict_do_nothing(index_elements=['event_id'])
                )
                inserted += int(result.rowcount or 0)
            return inserted
