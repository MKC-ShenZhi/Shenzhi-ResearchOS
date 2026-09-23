"""PostgreSQL implementation of Agent session persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.database import get_session_factory, session_scope
from app.core.errors import BusinessError
from app.models.agent_session import AgentSessionRow, AgentTurnRow
from app.services.agent_sessions.entities import AgentSession, AgentTurn
from app.services.agent_sessions.repository import (
    _populate_legacy_turns, decode_cursor, encode_cursor, new_session_id, new_turn_id,
)


def _ts(value: datetime | None) -> float | None:
    return value.timestamp() if value is not None else None


def _turn_from_row(row: AgentTurnRow) -> AgentTurn:
    return AgentTurn(
        id=row.id, session_id=row.session_id, user_content=row.user_content,
        settings=dict(row.settings), assistant_content=row.assistant_content,
        reasoning=row.reasoning, process=list(row.process), steers=list(row.steers),
        report=row.report, sources=list(row.sources), question=row.question,
        warnings=list(row.warnings), error=row.error, stopped=row.stopped,
        stop_reason=row.stop_reason, status=row.status, usage=dict(row.usage),
        transcript=list(row.transcript), created_at=_ts(row.created_at) or 0,
        completed_at=_ts(row.completed_at),
    )


def _session_from_row(row: AgentSessionRow, *, with_turns: bool = True) -> AgentSession:
    return AgentSession(
        id=row.id, owner=row.owner, title=row.title, settings=dict(row.settings),
        branched_from=row.branched_from, import_key=row.import_key,
        created_at=_ts(row.created_at) or 0, updated_at=_ts(row.updated_at) or 0,
        turns=[_turn_from_row(item) for item in row.turns] if with_turns else [],
    )


def _turn_row(turn: AgentTurn) -> AgentTurnRow:
    return AgentTurnRow(
        id=turn.id, session_id=turn.session_id, user_content=turn.user_content,
        settings=turn.settings, assistant_content=turn.assistant_content,
        reasoning=turn.reasoning, process=turn.process, steers=turn.steers,
        report=turn.report, sources=turn.sources, question=turn.question,
        warnings=turn.warnings, error=turn.error, stopped=turn.stopped,
        stop_reason=turn.stop_reason, status=turn.status, usage=turn.usage,
        transcript=turn.transcript,
        created_at=datetime.fromtimestamp(turn.created_at, timezone.utc),
        completed_at=(datetime.fromtimestamp(turn.completed_at, timezone.utc)
                      if turn.completed_at else None),
    )


class PostgresAgentSessionRepository:
    is_durable = True

    async def recover(self) -> None:
        async with session_scope() as db:
            running_sessions = list((await db.scalars(
                select(AgentTurnRow.session_id).where(AgentTurnRow.status == 'running')
            )).all())
            await db.execute(
                update(AgentTurnRow).where(AgentTurnRow.status == 'running').values(
                    status='failed', stopped=True, stop_reason='backend_restart',
                    error='backend restarted while generating', completed_at=func.now(),
                )
            )
            if running_sessions:
                await db.execute(
                    update(AgentSessionRow).where(AgentSessionRow.id.in_(running_sessions))
                    .values(updated_at=func.now())
                )

    async def create(self, owner: str, prompt: str, settings: dict,
                     branched_from: str | None = None) -> AgentSession:
        now = datetime.now(timezone.utc)
        row = AgentSessionRow(
            id=new_session_id(), owner=owner, title=prompt.strip()[:50] or '新会话',
            settings=dict(settings), branched_from=branched_from, created_at=now, updated_at=now,
        )
        async with session_scope() as db:
            db.add(row)
        return _session_from_row(row, with_turns=False)

    async def get(self, session_id: str, owner: str) -> AgentSession:
        async with get_session_factory()() as db:
            row = await db.scalar(
                select(AgentSessionRow)
                .where(AgentSessionRow.id == session_id, AgentSessionRow.owner == owner)
                .options(selectinload(AgentSessionRow.turns))
            )
        if row is None:
            raise BusinessError(20004, 'Agent 会话不存在或无权访问', 404)
        return _session_from_row(row)

    async def list_page(self, owner: str, limit: int, cursor: str | None) -> dict:
        boundary = decode_cursor(cursor)
        query = select(AgentSessionRow).where(AgentSessionRow.owner == owner)
        if boundary:
            cursor_time = datetime.fromtimestamp(boundary[0], timezone.utc)
            query = query.where(or_(
                AgentSessionRow.updated_at < cursor_time,
                and_(AgentSessionRow.updated_at == cursor_time, AgentSessionRow.id < boundary[1]),
            ))
        query = query.order_by(AgentSessionRow.updated_at.desc(), AgentSessionRow.id.desc()).limit(limit + 1)
        async with get_session_factory()() as db:
            rows = list((await db.scalars(query)).all())
        has_more = len(rows) > limit
        page = rows[:limit]
        sessions = [_session_from_row(row, with_turns=False) for row in page]
        return {
            'sessions': [item.summary() for item in sessions],
            'next_cursor': encode_cursor(sessions[-1].updated_at, sessions[-1].id)
                           if has_more and sessions else None,
            'has_more': has_more,
        }

    async def update_title(self, session_id: str, owner: str, title: str) -> AgentSession:
        value = title.strip()
        if not value:
            raise BusinessError(20001, '会话名称不能为空')
        async with session_scope() as db:
            row = await db.scalar(
                update(AgentSessionRow)
                .where(AgentSessionRow.id == session_id, AgentSessionRow.owner == owner)
                .values(title=value, updated_at=func.now()).returning(AgentSessionRow)
            )
        if row is None:
            raise BusinessError(20004, 'Agent 会话不存在或无权访问', 404)
        return _session_from_row(row, with_turns=False)

    async def delete(self, session_id: str, owner: str) -> None:
        async with session_scope() as db:
            found = await db.scalar(select(AgentSessionRow.id).where(
                AgentSessionRow.id == session_id, AgentSessionRow.owner == owner,
            ))
            if found is None:
                raise BusinessError(20004, 'Agent 会话不存在或无权访问', 404)
            running = await db.scalar(
                select(exists().where(
                    AgentTurnRow.session_id == session_id, AgentTurnRow.status == 'running',
                ))
            )
            if running:
                raise BusinessError(20009, '请先停止当前 Agent 运行', 409)
            deleted = await db.scalar(
                delete(AgentSessionRow)
                .where(AgentSessionRow.id == session_id, AgentSessionRow.owner == owner)
                .returning(AgentSessionRow.id)
            )
        if deleted is None:
            raise BusinessError(20004, 'Agent 会话不存在或无权访问', 404)

    async def start_turn(self, session_id: str, owner: str, prompt: str,
                         settings: dict, warnings: list[str]) -> AgentTurn:
        turn = AgentTurn(new_turn_id(), session_id, prompt, dict(settings), warnings=list(warnings))
        try:
            async with session_scope() as db:
                found = await db.scalar(select(AgentSessionRow.id).where(
                    AgentSessionRow.id == session_id, AgentSessionRow.owner == owner,
                ))
                if found is None:
                    raise BusinessError(20004, 'Agent 会话不存在或无权访问', 404)
                db.add(_turn_row(turn))
                await db.execute(
                    update(AgentSessionRow).where(AgentSessionRow.id == session_id)
                    .values(settings=dict(settings), updated_at=func.now())
                )
                await db.flush()
        except IntegrityError:
            raise BusinessError(20009, '该会话已有正在运行的任务', 409) from None
        return turn

    async def finish_turn(self, session_id: str, owner: str, turn_id: str,
                          payload: dict[str, Any]) -> AgentTurn:
        allowed = {
            'assistant_content', 'reasoning', 'process', 'steers', 'report', 'sources',
            'question', 'warnings', 'error', 'stopped', 'stop_reason', 'status', 'usage', 'transcript',
        }
        values = {key: value for key, value in payload.items() if key in allowed}
        values['completed_at'] = func.now()
        async with session_scope() as db:
            owner_exists = select(AgentSessionRow.id).where(
                AgentSessionRow.id == session_id, AgentSessionRow.owner == owner,
            ).exists()
            row = await db.scalar(
                update(AgentTurnRow)
                .where(AgentTurnRow.id == turn_id, AgentTurnRow.session_id == session_id,
                       AgentTurnRow.status == 'running', owner_exists)
                .values(**values).returning(AgentTurnRow)
            )
            if row is not None:
                await db.execute(
                    update(AgentSessionRow).where(AgentSessionRow.id == session_id)
                    .values(updated_at=func.now())
                )
        if row is None:
            raise BusinessError(20004, 'Agent 轮次不存在或已经结束', 404)
        return _turn_from_row(row)

    async def import_legacy(self, owner: str, payload: dict[str, Any]) -> AgentSession:
        import_key = str(payload['import_key'])
        async with get_session_factory()() as db:
            existing = await db.scalar(select(AgentSessionRow).where(
                AgentSessionRow.owner == owner, AgentSessionRow.import_key == import_key,
            ).options(selectinload(AgentSessionRow.turns)))
        if existing is not None:
            return _session_from_row(existing)

        created = float(payload.get('created_at') or datetime.now(timezone.utc).timestamp())
        updated = float(payload.get('updated_at') or created)
        session = AgentSession(
            id=new_session_id(), owner=owner, title=str(payload.get('title') or '本地会话')[:200],
            branched_from=payload.get('branched_from'), import_key=import_key,
            created_at=created, updated_at=updated,
        )
        _populate_legacy_turns(session, payload.get('turns') or [])
        row = AgentSessionRow(
            id=session.id, owner=owner, title=session.title, settings={},
            branched_from=session.branched_from, import_key=import_key,
            created_at=datetime.fromtimestamp(created, timezone.utc),
            updated_at=datetime.fromtimestamp(updated, timezone.utc),
        )
        try:
            async with session_scope() as db:
                row.turns = [_turn_row(turn) for turn in session.turns]
                db.add(row)
        except IntegrityError:
            # Idempotent retry raced another request. Return the winner.
            async with get_session_factory()() as db:
                existing = await db.scalar(select(AgentSessionRow).where(
                    AgentSessionRow.owner == owner, AgentSessionRow.import_key == import_key,
                ).options(selectinload(AgentSessionRow.turns)))
            if existing is None:
                raise
            return _session_from_row(existing)
        return session

    async def claim_anonymous_sessions(self, source_owner: str, target_owner: str) -> dict:
        running_exists = exists(select(AgentTurnRow.id).where(
            AgentTurnRow.session_id == AgentSessionRow.id, AgentTurnRow.status == 'running',
        ))
        async with session_scope() as db:
            skipped = await db.scalar(select(func.count()).select_from(AgentSessionRow).where(
                AgentSessionRow.owner == source_owner, running_exists,
            ))
            moved = await db.scalars(
                update(AgentSessionRow)
                .where(AgentSessionRow.owner == source_owner, ~running_exists)
                .values(owner=target_owner, updated_at=func.now()).returning(AgentSessionRow.id)
            )
            count = len(moved.all())
        return {'moved_count': count, 'skipped_running_count': int(skipped or 0), 'durable': True}

    async def purge_owner(self, owner: str) -> int:
        async with session_scope() as db:
            deleted = await db.scalars(
                delete(AgentSessionRow).where(AgentSessionRow.owner == owner)
                .returning(AgentSessionRow.id)
            )
            return len(deleted.all())

    async def close(self) -> None:
        # The shared database engine is owned and disposed by the Chat repository.
        return None
