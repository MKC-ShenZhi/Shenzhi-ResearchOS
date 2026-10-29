"""Build and atomically publish one platform day of aggregate counts."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.collections import CollectionFolderRow, CollectionItemRow
from app.models.interactions import PaperLikeRow, TopicFollowRow
from app.models.stats import PaperStatDailyRow, StatsSnapshotRunRow, TopicStatDailyRow
from app.services.topics.registry import TopicRegistry


SNAPSHOT_VERSION = 'v1'
SHANGHAI_TIMEZONE = ZoneInfo('Asia/Shanghai')
INSERT_CHUNK_SIZE = 1000
logger = logging.getLogger(__name__)


def shanghai_today() -> date:
    return utc_now().astimezone(SHANGHAI_TIMEZONE).date()


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_date: date
    snapshot_version: str
    computed_at: datetime
    paper_count: int
    topic_count: int


class SnapshotService:
    """Re-runnable per day; a complete build replaces that day atomically.

    The publication marker and every aggregate row for the day are written in
    one transaction. If any step fails the transaction rolls back, so readers
    keep seeing the previous complete publication instead of partial counts.
    """

    def __init__(self, registry: TopicRegistry | None = None):
        self.registry = registry or TopicRegistry()

    async def build(self, snapshot_date: date | None = None) -> SnapshotResult:
        target = snapshot_date or shanghai_today()
        try:
            result = await self._publish(target)
        except Exception as error:
            logger.exception(
                'stats.snapshot.failed date=%s error_type=%s', target.isoformat(), type(error).__name__,
            )
            await self._record_failure(target, error)
            raise
        logger.info(
            'stats.snapshot.published date=%s papers=%d topics=%d',
            result.snapshot_date.isoformat(), result.paper_count, result.topic_count,
        )
        return result

    async def _publish(self, target: date) -> SnapshotResult:
        topic_ids = [topic.id for topic in self.registry.list_topics().items]
        async with session_scope() as session:
            # LOCK precedes the first MVCC read. Serialize builders before taking
            # a repeatable snapshot, including two simultaneous first builds.
            # Ordinary readers remain unblocked by this table lock.
            await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            await session.execute(text('LOCK TABLE stats_snapshot_runs IN SHARE ROW EXCLUSIVE MODE'))
            computed_at = utc_now()
            collector_counts = await self._collector_counts(session)
            like_counts = await self._like_counts(session)
            follower_counts = await self._follower_counts(session)
            paper_ids = sorted(set(collector_counts) | set(like_counts))

            # Publish the day first so the foreign key is satisfied; rows and the
            # completed marker commit together.
            await session.execute(
                insert(StatsSnapshotRunRow)
                .values(
                    snapshot_date=target,
                    status='completed',
                    snapshot_version=SNAPSHOT_VERSION,
                    computed_at=computed_at,
                    updated_at=computed_at,
                    failure_reason=None,
                )
                .on_conflict_do_update(
                    index_elements=['snapshot_date'],
                    set_={
                        'status': 'completed',
                        'snapshot_version': SNAPSHOT_VERSION,
                        'computed_at': computed_at,
                        'updated_at': computed_at,
                        'failure_reason': None,
                    },
                )
            )
            await session.execute(
                delete(PaperStatDailyRow).where(PaperStatDailyRow.snapshot_date == target)
            )
            await session.execute(
                delete(TopicStatDailyRow).where(TopicStatDailyRow.snapshot_date == target)
            )
            for chunk in _chunks(paper_ids):
                await session.execute(insert(PaperStatDailyRow).values([
                    {
                        'snapshot_date': target,
                        'paper_id': paper_id,
                        'collector_count': collector_counts.get(paper_id, 0),
                        'like_count': like_counts.get(paper_id, 0),
                    }
                    for paper_id in chunk
                ]))
            for chunk in _chunks(topic_ids):
                await session.execute(insert(TopicStatDailyRow).values([
                    {
                        'snapshot_date': target,
                        'topic_id': topic_id,
                        'follower_count': follower_counts.get(topic_id, 0),
                    }
                    for topic_id in chunk
                ]))

        return SnapshotResult(
            snapshot_date=target,
            snapshot_version=SNAPSHOT_VERSION,
            computed_at=computed_at,
            paper_count=len(paper_ids),
            topic_count=len(topic_ids),
        )

    @staticmethod
    async def _collector_counts(session: AsyncSession) -> dict[str, int]:
        rows = await session.execute(
            select(
                CollectionItemRow.paper_id,
                func.count(func.distinct(CollectionFolderRow.user_id)),
            )
            .join(CollectionFolderRow, CollectionFolderRow.id == CollectionItemRow.folder_id)
            .group_by(CollectionItemRow.paper_id)
        )
        return {paper_id: int(total) for paper_id, total in rows}

    @staticmethod
    async def _like_counts(session: AsyncSession) -> dict[str, int]:
        rows = await session.execute(
            select(PaperLikeRow.paper_id, func.count(func.distinct(PaperLikeRow.user_id)))
            .group_by(PaperLikeRow.paper_id)
        )
        return {paper_id: int(total) for paper_id, total in rows}

    @staticmethod
    async def _follower_counts(session: AsyncSession) -> dict[str, int]:
        rows = await session.execute(
            select(TopicFollowRow.topic_id, func.count(func.distinct(TopicFollowRow.user_id)))
            .group_by(TopicFollowRow.topic_id)
        )
        return {topic_id: int(total) for topic_id, total in rows}

    async def _record_failure(self, target: date, error: Exception) -> None:
        """Record the failed attempt without hiding an already complete day."""
        reason = type(error).__name__
        try:
            async with session_scope() as session:
                run = await session.get(StatsSnapshotRunRow, target)
                now = utc_now()
                if run is None:
                    session.add(StatsSnapshotRunRow(
                        snapshot_date=target,
                        status='failed',
                        snapshot_version=SNAPSHOT_VERSION,
                        updated_at=now,
                        failure_reason=reason,
                    ))
                elif run.status == 'completed':
                    run.failure_reason = reason
                    run.updated_at = now
                else:
                    run.status = 'failed'
                    run.failure_reason = reason
                    run.updated_at = now
        except Exception:
            logger.exception('stats.snapshot.failure_not_recorded date=%s', target.isoformat())


def _chunks(values: list[str]) -> list[list[str]]:
    return [
        values[index:index + INSERT_CHUNK_SIZE]
        for index in range(0, len(values), INSERT_CHUNK_SIZE)
    ]
