"""Read side of the published daily platform aggregates.

Only ``status='completed'`` runs are served. Rows for one day are written in a
single transaction, so a reader never observes a partially rebuilt day.
"""
from __future__ import annotations

import base64
import binascii
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.stats import PaperStatDailyRow, StatsSnapshotRunRow, TopicStatDailyRow
from app.schemas.stats import (
    PaperStatsItem,
    PaperStatsPage,
    StatsMetaResponse,
    TopicStatsItem,
    TopicStatsPage,
)


MAX_LOOKUP_IDS = 100
MAX_CURSOR_ID_LENGTH = 300


class StatsCursorError(ValueError):
    """The opaque cursor cannot address the requested published day."""


def _encode_cursor(run: StatsSnapshotRunRow, after: str, kind: str) -> str:
    raw = json.dumps({
        'd': run.snapshot_date.isoformat(), 'a': after,
        'c': run.computed_at.isoformat(), 'k': kind,
    }, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _decode_cursor(cursor: str) -> tuple[date, str, datetime, str]:
    try:
        padding = '=' * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b'-_', validate=True)
        value: Any = json.loads(raw)
        snapshot_date = date.fromisoformat(value['d'])
        after = value['a']
        computed_at = datetime.fromisoformat(value['c'])
        kind = value['k']
    except (
        binascii.Error, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError,
    ) as error:
        raise StatsCursorError('分页游标无效') from error
    if (
        not isinstance(after, str)
        or not after
        or len(after) > MAX_CURSOR_ID_LENGTH
        or snapshot_date.isoformat() != value['d']
        or computed_at.tzinfo is None
        or kind not in ('papers', 'topics')
    ):
        raise StatsCursorError('分页游标无效')
    return snapshot_date, after, computed_at, kind


class PlatformStatsService:
    async def meta(self) -> StatsMetaResponse:
        async with session_scope() as session:
            run = await self._latest_run(session)
        if run is None:
            return StatsMetaResponse(published=False)
        return StatsMetaResponse(
            published=True,
            snapshot_date=run.snapshot_date,
            snapshot_version=run.snapshot_version,
            computed_at=run.computed_at,
        )

    async def papers_page(
        self,
        *,
        snapshot_date: date | None,
        limit: int,
        cursor: str | None = None,
        paper_ids: list[str] | None = None,
    ) -> PaperStatsPage:
        requested = list(dict.fromkeys(paper_ids)) if paper_ids is not None else None
        async with session_scope() as session:
            await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            run, after = await self._resolve(session, snapshot_date, cursor, 'papers')
            if requested is not None:
                if after is not None:
                    raise BusinessError(20001, '按论文 ID 查询时不能同时使用分页游标', 400)
                rows = list(await session.scalars(
                    select(PaperStatDailyRow).where(
                        PaperStatDailyRow.snapshot_date == run.snapshot_date,
                        PaperStatDailyRow.paper_id.in_(requested),
                    )
                ))
                found = {row.paper_id: row for row in rows}
                return PaperStatsPage(
                    **_run_fields(run),
                    items=[
                        PaperStatsItem(
                            paper_id=paper_id,
                            collector_count=found[paper_id].collector_count,
                            like_count=found[paper_id].like_count,
                        )
                        for paper_id in requested
                        if paper_id in found
                    ],
                    total=len(found),
                    missing_paper_ids=[paper_id for paper_id in requested if paper_id not in found],
                )

            total = await self._count(session, PaperStatDailyRow, run.snapshot_date)
            query = (
                select(PaperStatDailyRow)
                .where(PaperStatDailyRow.snapshot_date == run.snapshot_date)
                .order_by(PaperStatDailyRow.paper_id)
                .limit(limit + 1)
            )
            if after is not None:
                query = query.where(PaperStatDailyRow.paper_id > after)
            rows = list(await session.scalars(query))
        has_more = len(rows) > limit
        page = rows[:limit]
        return PaperStatsPage(
            **_run_fields(run),
            items=[
                PaperStatsItem(
                    paper_id=row.paper_id,
                    collector_count=row.collector_count,
                    like_count=row.like_count,
                )
                for row in page
            ],
            total=total,
            next_cursor=_encode_cursor(run, page[-1].paper_id, 'papers') if has_more and page else None,
            has_more=has_more,
        )

    async def topics_page(
        self,
        *,
        snapshot_date: date | None,
        limit: int,
        cursor: str | None = None,
        topic_ids: list[str] | None = None,
    ) -> TopicStatsPage:
        requested = list(dict.fromkeys(topic_ids)) if topic_ids is not None else None
        async with session_scope() as session:
            await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            run, after = await self._resolve(session, snapshot_date, cursor, 'topics')
            if requested is not None:
                if after is not None:
                    raise BusinessError(20001, '按主题 ID 查询时不能同时使用分页游标', 400)
                rows = list(await session.scalars(
                    select(TopicStatDailyRow).where(
                        TopicStatDailyRow.snapshot_date == run.snapshot_date,
                        TopicStatDailyRow.topic_id.in_(requested),
                    )
                ))
                found = {row.topic_id: row for row in rows}
                return TopicStatsPage(
                    **_run_fields(run),
                    items=[
                        TopicStatsItem(
                            topic_id=topic_id,
                            follower_count=found[topic_id].follower_count,
                        )
                        for topic_id in requested
                        if topic_id in found
                    ],
                    total=len(found),
                    missing_topic_ids=[topic_id for topic_id in requested if topic_id not in found],
                )

            total = await self._count(session, TopicStatDailyRow, run.snapshot_date)
            query = (
                select(TopicStatDailyRow)
                .where(TopicStatDailyRow.snapshot_date == run.snapshot_date)
                .order_by(TopicStatDailyRow.topic_id)
                .limit(limit + 1)
            )
            if after is not None:
                query = query.where(TopicStatDailyRow.topic_id > after)
            rows = list(await session.scalars(query))
        has_more = len(rows) > limit
        page = rows[:limit]
        return TopicStatsPage(
            **_run_fields(run),
            items=[
                TopicStatsItem(topic_id=row.topic_id, follower_count=row.follower_count)
                for row in page
            ],
            total=total,
            next_cursor=_encode_cursor(run, page[-1].topic_id, 'topics') if has_more and page else None,
            has_more=has_more,
        )

    async def _resolve(
        self, session: AsyncSession, requested: date | None, cursor: str | None, kind: str,
    ) -> tuple[StatsSnapshotRunRow, str | None]:
        after: str | None = None
        cursor_date: date | None = None
        cursor_computed_at: datetime | None = None
        if cursor is not None:
            try:
                cursor_date, after, cursor_computed_at, cursor_kind = _decode_cursor(cursor)
            except StatsCursorError as error:
                raise BusinessError(20001, str(error), 400) from error
            if requested is not None and requested != cursor_date:
                raise BusinessError(20001, '分页游标与请求日期不一致', 400)
            if cursor_kind != kind:
                raise BusinessError(20001, '分页游标与统计类型不一致', 400)

        target = requested or cursor_date
        if target is None:
            run = await self._latest_run(session)
            if run is None:
                raise BusinessError(40401, '暂无已发布的统计快照', 404)
            return run, after

        run = await session.get(StatsSnapshotRunRow, target)
        if run is None or run.status != 'completed' or run.computed_at is None:
            raise BusinessError(40401, '该日期暂无已发布的统计快照', 404)
        if cursor_computed_at is not None and cursor_computed_at != run.computed_at:
            raise BusinessError(20001, '统计快照已更新，请从第一页重新读取', 409)
        return run, after

    @staticmethod
    async def _latest_run(session: AsyncSession) -> StatsSnapshotRunRow | None:
        return await session.scalar(
            select(StatsSnapshotRunRow)
            .where(
                StatsSnapshotRunRow.status == 'completed',
                StatsSnapshotRunRow.computed_at.is_not(None),
            )
            .order_by(StatsSnapshotRunRow.snapshot_date.desc())
            .limit(1)
        )

    @staticmethod
    async def _count(session: AsyncSession, model, snapshot_date: date) -> int:
        return int(await session.scalar(
            select(func.count()).select_from(model).where(model.snapshot_date == snapshot_date)
        ) or 0)


def _run_fields(run: StatsSnapshotRunRow) -> dict[str, Any]:
    return {
        'snapshot_date': run.snapshot_date,
        'snapshot_version': run.snapshot_version,
        'computed_at': run.computed_at,
    }
