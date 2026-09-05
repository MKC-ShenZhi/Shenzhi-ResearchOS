"""PostgreSQL-backed session repository with in-process active message cache."""
import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import selectinload

from app.core.database import dispose_engine, get_session_factory, session_scope
from app.core.errors import BusinessError
from app.models.chat import ChatMessageRow, ChatSessionRow
from app.services.session_entities import Message, Session

TERMINAL = frozenset({'done', 'stopped', 'failed'})
RECOVER_ERROR = 'backend restarted while generating'


def _ts(value: datetime) -> float:
    return value.timestamp()


def _message_from_row(row: ChatMessageRow) -> Message:
    return Message(
        str(row.id), str(row.session_id), row.question, dict(row.settings),
        row.attachment_context, list(row.warnings), row.content, row.reasoning,
        row.status, list(row.message_refs), list(row.followups), row.duration_ms, row.error,
    )


def _session_from_row(row: ChatSessionRow, messages: list[Message]) -> Session:
    return Session(
        str(row.id), row.owner, row.title, dict(row.settings), row.favorite,
        _ts(row.updated_at), messages,
    )


class PostgresSessionRepository:
    """Durable sessions in PostgreSQL; active streaming state stays in-process."""

    is_durable = True
    max_sessions = 500  # unused for PG list cap in 2a; kept for test patch compatibility

    def __init__(self) -> None:
        self.messages: dict[str, Message] = {}
        self.uploads: dict[str, dict] = {}
        self.ttl = 86400

    def _track(self, message: Message) -> None:
        self.messages[message.id] = message

    def _untrack(self, message_id: str) -> None:
        self.messages.pop(message_id, None)

    def _overlay_messages(self, messages: list[Message]) -> list[Message]:
        return [self.messages.get(message.id, message) for message in messages]

    async def recover(self) -> None:
        async with session_scope() as db:
            await db.execute(
                update(ChatMessageRow)
                .where(ChatMessageRow.status == 'streaming')
                .values(status='failed', error=RECOVER_ERROR, completed_at=func.now())
            )
        for message in self.messages.values():
            if message.status == 'streaming':
                message.status = 'failed'
                message.error = RECOVER_ERROR

    async def persist_message(self, message: Message) -> None:
        message_id = uuid.UUID(message.id)
        session_id = uuid.UUID(message.session_id)
        async with session_scope() as db:
            if message.status == 'streaming':
                await db.execute(
                    update(ChatMessageRow)
                    .where(ChatMessageRow.id == message_id)
                    .where(ChatMessageRow.status.in_(('stopped', 'failed')))
                    .values(status='streaming', error=None, completed_at=None)
                )
            else:
                await db.execute(
                    update(ChatMessageRow)
                    .where(ChatMessageRow.id == message_id)
                    .where(ChatMessageRow.status == 'streaming')
                    .values(
                        content=message.content,
                        reasoning=message.reasoning,
                        status=message.status,
                        message_refs=message.references,
                        followups=message.followups,
                        duration_ms=message.duration_ms,
                        error=message.error,
                        settings=dict(message.settings),
                        completed_at=func.now(),
                    )
                )
            await db.execute(
                update(ChatSessionRow)
                .where(ChatSessionRow.id == session_id)
                .values(updated_at=func.now())
            )
        if message.status in TERMINAL:
            self._untrack(message.id)
        elif message.status == 'streaming':
            self._track(message)

    async def create(self, owner: str, question: str, settings: dict) -> Session:
        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        async with session_scope() as db:
            db.add(ChatSessionRow(
                id=session_id, owner=owner, title=question[:50], settings=dict(settings),
                favorite=False, created_at=now, updated_at=now,
            ))
        return Session(str(session_id), owner, question[:50], dict(settings))

    async def get(self, session_id: str, owner: str) -> Session:
        sid = uuid.UUID(session_id)
        async with get_session_factory()() as db:
            row = await db.scalar(
                select(ChatSessionRow)
                .where(ChatSessionRow.id == sid, ChatSessionRow.owner == owner)
                .options(selectinload(ChatSessionRow.messages))
            )
        if row is None:
            raise BusinessError(20004, '会话不存在或已过期', 404)
        messages = self._overlay_messages([_message_from_row(item) for item in row.messages])
        return _session_from_row(row, messages)

    async def session_for_message(self, message: Message) -> Session:
        async with get_session_factory()() as db:
            row = await db.scalar(
                select(ChatSessionRow)
                .where(ChatSessionRow.id == uuid.UUID(message.session_id))
                .options(selectinload(ChatSessionRow.messages))
            )
        if row is None:
            raise BusinessError(20004, '会话不存在或已过期', 404)
        messages = self._overlay_messages([_message_from_row(item) for item in row.messages])
        tracked = self.messages.get(message.id)
        if tracked is not None:
            messages = [tracked if item.id == message.id else item for item in messages]
        session = _session_from_row(row, messages)
        if not any(item is message for item in session.messages):
            if tracked is not None:
                session.messages = [tracked if item.id == message.id else item for item in session.messages]
            elif not any(item.id == message.id for item in session.messages):
                raise BusinessError(20004, '会话不存在或已过期', 404)
        return session

    async def message(self, message_id: str, owner: str) -> Message:
        if message_id in self.messages:
            message = self.messages[message_id]
            await self.get(message.session_id, owner)
            return message
        async with get_session_factory()() as db:
            result = await db.execute(
                select(ChatMessageRow, ChatSessionRow.owner)
                .join(ChatSessionRow, ChatMessageRow.session_id == ChatSessionRow.id)
                .where(ChatMessageRow.id == uuid.UUID(message_id))
            )
            row = result.first()
        if row is None:
            raise BusinessError(20004, '消息不存在或已过期', 404)
        msg_row, msg_owner = row
        if msg_owner != owner:
            raise BusinessError(20004, '消息不存在或已过期', 404)
        message = _message_from_row(msg_row)
        # Track so resume/stop/stream share one object with session.messages overlay.
        self._track(message)
        return message

    async def add_message(self, session: Session, question: str, settings: dict,
                          context: str = '', warnings: list[str] | None = None) -> Message:
        if any(item.status == 'streaming' for item in session.messages):
            raise BusinessError(20009, '请先停止当前生成', 409)
        if len(session.messages) >= 100:
            raise BusinessError(20009, '单个临时会话最多 100 轮，请新建会话', 429)
        message_id = uuid.uuid4()
        sid = uuid.UUID(session.id)
        now = datetime.now(timezone.utc)
        message = Message(
            str(message_id), session.id, question, dict(settings), context, warnings or [],
        )
        async with session_scope() as db:
            await db.execute(
                update(ChatSessionRow)
                .where(ChatSessionRow.id == sid)
                .values(settings=dict(settings), updated_at=now)
            )
            db.add(ChatMessageRow(
                id=message_id, session_id=sid, question=question, settings=dict(settings),
                attachment_context=context, warnings=warnings or [], status='streaming',
                created_at=now,
            ))
        session.messages.append(message)
        session.settings = dict(settings)
        session.updated_at = _ts(now)
        self._track(message)
        return message

    async def list(self, owner: str) -> list[dict]:
        async with get_session_factory()() as db:
            rows = await db.scalars(
                select(ChatSessionRow)
                .where(ChatSessionRow.owner == owner)
                .order_by(ChatSessionRow.favorite.desc(), ChatSessionRow.updated_at.desc())
            )
        return [_session_from_row(row, []).public() for row in rows.all()]

    async def update(self, session_id: str, owner: str, *, title: str | None = None,
                     favorite: bool | None = None) -> Session:
        session = await self.get(session_id, owner)
        if title is not None:
            if not title.strip():
                raise BusinessError(20001, '会话名称不能为空')
            session.title = title.strip()
        if favorite is not None:
            session.favorite = favorite
        session.updated_at = time.time()
        async with session_scope() as db:
            await db.execute(
                update(ChatSessionRow)
                .where(ChatSessionRow.id == uuid.UUID(session_id))
                .values(
                    **({'title': session.title} if title is not None else {}),
                    **({'favorite': session.favorite} if favorite is not None else {}),
                    updated_at=func.now(),
                )
            )
        return session

    async def touch(self, session_id: str) -> None:
        async with session_scope() as db:
            await db.execute(
                update(ChatSessionRow)
                .where(ChatSessionRow.id == uuid.UUID(session_id))
                .values(updated_at=func.now())
            )

    async def clear(self) -> None:
        self.messages.clear()
        self.uploads.clear()
        async with session_scope() as db:
            await db.execute(delete(ChatMessageRow))
            await db.execute(delete(ChatSessionRow))

    async def purge_owner(self, owner: str) -> None:
        """Delete one owner's sessions without wiping the shared development database."""
        async with get_session_factory()() as db:
            rows = (await db.scalars(
                select(ChatSessionRow.id).where(ChatSessionRow.owner == owner)
            )).all()
        for session_id in rows:
            sid = str(session_id)
            for message_id, message in list(self.messages.items()):
                if message.session_id == sid:
                    if message.task and not message.task.done():
                        message.task.cancel()
                    self._untrack(message_id)
        async with session_scope() as db:
            await db.execute(delete(ChatSessionRow).where(ChatSessionRow.owner == owner))

    async def delete(self, session_id: str, owner: str) -> None:
        session = await self.get(session_id, owner)
        for item in session.messages:
            if item.task and not item.task.done():
                item.task.cancel()
            self._untrack(item.id)
        async with session_scope() as db:
            await db.execute(
                delete(ChatSessionRow).where(
                    ChatSessionRow.id == uuid.UUID(session_id),
                    ChatSessionRow.owner == owner,
                )
            )

    async def claim_anonymous_sessions(self, source_owner: str, target_owner: str) -> dict:
        streaming_exists = exists(
            select(ChatMessageRow.id).where(
                ChatMessageRow.session_id == ChatSessionRow.id,
                ChatMessageRow.status == 'streaming',
            )
        )
        async with session_scope() as db:
            skipped = await db.scalar(
                select(func.count())
                .select_from(ChatSessionRow)
                .where(ChatSessionRow.owner == source_owner, streaming_exists)
            )
            moved = await db.scalars(
                update(ChatSessionRow)
                .where(ChatSessionRow.owner == source_owner, ~streaming_exists)
                .values(owner=target_owner, updated_at=func.now())
                .returning(ChatSessionRow.id)
            )
            moved_count = len(moved.all())
        return {
            'moved_count': moved_count,
            'skipped_streaming_count': int(skipped or 0),
            'durable': True,
        }

    async def purge_expired_anonymous_sessions(self, cutoff: datetime) -> int:
        """Remove only expired anonymous sessions; message rows cascade in PostgreSQL."""
        async with session_scope() as db:
            deleted = await db.scalars(
                delete(ChatSessionRow)
                .where(ChatSessionRow.owner.like('anon:%'), ChatSessionRow.updated_at < cutoff)
                .returning(ChatSessionRow.id)
            )
            session_ids = {str(session_id) for session_id in deleted.all()}
        for message_id, message in list(self.messages.items()):
            if message.session_id in session_ids:
                if message.task and not message.task.done():
                    message.task.cancel()
                self._untrack(message_id)
        return len(session_ids)

    def prune(self) -> None:
        cutoff = time.time() - self.ttl
        self.uploads = {key: value for key, value in self.uploads.items() if value['created_at'] > cutoff}

    def save_upload(self, owner: str, filename: str, parsed: dict) -> dict:
        self.prune()
        if len(self.uploads) >= 500:
            raise BusinessError(20009, '临时附件容量已满，请稍后重试', 429)
        file_id = str(uuid.uuid4())
        self.uploads[file_id] = {**parsed, 'file_id': file_id, 'filename': filename,
                                 'owner': owner, 'created_at': time.time(), 'parse_status': 'ok'}
        return self.upload(file_id, owner)

    def upload(self, file_id: str, owner: str) -> dict:
        item = self.uploads.get(file_id)
        if not item or item['owner'] != owner or item['created_at'] < time.time() - self.ttl:
            raise BusinessError(20004, '附件不存在或已过期，请重新上传', 404)
        return item

    async def close(self) -> None:
        tasks = [item.task for item in self.messages.values() if item.task and not item.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await dispose_engine()
