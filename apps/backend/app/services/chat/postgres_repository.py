"""PostgreSQL-backed session repository with in-process active message cache."""
import asyncio
import time
import uuid
from datetime import datetime, timezone
from sqlalchemy import delete, exists, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.database import dispose_engine, get_session_factory, session_scope
from app.core.errors import BusinessError
from app.core.idempotency import ensure_same_request
from app.core.worker_lease import LEASE_SECONDS, current_worker_id
from app.models.chat import ChatMessageRow, ChatSessionRow
from app.services.chat.entities import Message, Session

TERMINAL = frozenset({'done', 'stopped', 'failed'})
RECOVER_ERROR = 'backend restarted while generating'


def _ts(value: datetime) -> float:
    return value.timestamp()


def _constraint_name(error: IntegrityError) -> str | None:
    for cause in (error.orig, getattr(error.orig, '__cause__', None)):
        name = getattr(cause, 'constraint_name', None)
        if isinstance(name, str):
            return name
    return None


def _message_from_row(row: ChatMessageRow) -> Message:
    return Message(
        str(row.id), str(row.session_id), row.question, dict(row.settings),
        row.attachment_context, list(row.warnings), row.content, row.reasoning,
        row.status, list(row.message_refs), list(row.followups), row.duration_ms, row.error,
        idempotency_owner=row.idempotency_owner,
        idempotency_scope=row.idempotency_scope,
        idempotency_key=row.idempotency_key,
        idempotency_fingerprint=row.idempotency_fingerprint,
        generation_claimed=row.generation_claimed,
        worker_id=row.worker_id,
        lease_expires_at=row.lease_expires_at,
    )


def _lease_deadline():
    return func.clock_timestamp() + text(f"INTERVAL '{LEASE_SECONDS} seconds'")


def _sync_message_from_row(message: Message, row: ChatMessageRow) -> None:
    message.content = row.content
    message.reasoning = row.reasoning
    message.status = row.status
    message.references = list(row.message_refs)
    message.followups = list(row.followups)
    message.duration_ms = row.duration_ms
    message.error = row.error
    message.warnings = list(row.warnings)
    message.settings = dict(row.settings)
    message.generation_claimed = row.generation_claimed
    message.worker_id = row.worker_id
    message.lease_expires_at = row.lease_expires_at


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

    def _local_message(self, message_id: str) -> Message | None:
        """Return the cached object only while this worker owns its generation task.

        Any other cached copy may be stale after another worker finished the row,
        so the database stays authoritative for it.
        """
        message = self.messages.get(message_id)
        return message if message is not None and message.task is not None else None

    def _overlay_messages(self, messages: list[Message]) -> list[Message]:
        return [self._local_message(message.id) or message for message in messages]

    async def _recover_expired_messages(self, db, *, session_id=None, message_id=None) -> set[str]:
        statement = update(ChatMessageRow).where(
            ChatMessageRow.status == 'streaming',
            ChatMessageRow.lease_expires_at <= func.clock_timestamp(),
        )
        if session_id is not None:
            statement = statement.where(ChatMessageRow.session_id == session_id)
        if message_id is not None:
            statement = statement.where(ChatMessageRow.id == message_id)
        recovered = await db.scalars(
            statement.values(
                status='failed', error=RECOVER_ERROR, completed_at=func.clock_timestamp(),
                worker_id=None, lease_expires_at=None,
            ).returning(ChatMessageRow.id)
        )
        return {str(item) for item in recovered.all()}

    def _sync_recovered_messages(self, recovered_ids: set[str]) -> None:
        for message_id in recovered_ids:
            message = self.messages.get(message_id)
            if message is not None:
                message.status = 'failed'
                message.error = RECOVER_ERROR
                message.worker_id = None
                message.lease_expires_at = None

    async def recover(self) -> None:
        async with session_scope() as db:
            recovered_ids = await self._recover_expired_messages(db)
        self._sync_recovered_messages(recovered_ids)

    async def persist_message(self, message: Message, worker_id: str | None = None) -> bool:
        message_id = uuid.UUID(message.id)
        session_id = uuid.UUID(message.session_id)
        async with session_scope() as db:
            if message.status == 'streaming':
                persisted = await db.scalar(
                    update(ChatMessageRow)
                    .where(ChatMessageRow.id == message_id)
                    .where(ChatMessageRow.status.in_(('stopped', 'failed')))
                    .values(status='streaming', error=None, completed_at=None,
                            generation_claimed=False, worker_id=None,
                            lease_expires_at=_lease_deadline())
                    .returning(ChatMessageRow.id)
                )
            else:
                statement = (
                    update(ChatMessageRow)
                    .where(ChatMessageRow.id == message_id)
                    .where(ChatMessageRow.status == 'streaming')
                )
                if worker_id is not None:
                    statement = statement.where(
                        ChatMessageRow.worker_id == worker_id,
                        ChatMessageRow.lease_expires_at > func.clock_timestamp(),
                    )
                else:
                    # Only a row no worker has claimed may be finalized without
                    # a lease owner, e.g. a stop before the SSE stream started.
                    statement = statement.where(
                        ChatMessageRow.generation_claimed.is_(False),
                        ChatMessageRow.worker_id.is_(None),
                    )
                persisted = await db.scalar(
                    statement.values(
                        content=message.content,
                        reasoning=message.reasoning,
                        status=message.status,
                        message_refs=message.references,
                        followups=message.followups,
                        duration_ms=message.duration_ms,
                        error=message.error,
                        settings=dict(message.settings),
                        warnings=list(message.warnings),
                        completed_at=func.clock_timestamp(),
                        worker_id=worker_id,
                        lease_expires_at=None,
                    ).returning(ChatMessageRow.id)
                )
            if persisted is not None:
                await db.execute(
                    update(ChatSessionRow)
                    .where(ChatSessionRow.id == session_id)
                    .values(updated_at=func.clock_timestamp())
                )
        if message.status in TERMINAL:
            self._untrack(message.id)
        elif message.status == 'streaming':
            self._track(message)
        return persisted is not None

    async def create(self, owner: str, question: str, settings: dict) -> Session:
        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        async with session_scope() as db:
            db.add(ChatSessionRow(
                id=session_id, owner=owner, title=question[:50], settings=dict(settings),
                favorite=False, created_at=now, updated_at=now,
            ))
        return Session(str(session_id), owner, question[:50], dict(settings))

    async def find_idempotent_message(self, owner: str, scope: str, key: str,
                                      fingerprint: str) -> Message | None:
        recovered_ids: set[str] = set()
        async with session_scope() as db:
            row = await db.scalar(
                select(ChatMessageRow)
                .join(ChatSessionRow, ChatMessageRow.session_id == ChatSessionRow.id)
                .where(
                    ChatSessionRow.owner == owner,
                    ChatMessageRow.idempotency_owner == owner,
                    ChatMessageRow.idempotency_scope == scope,
                    ChatMessageRow.idempotency_key == key,
                )
            )
            if row is not None:
                ensure_same_request(row.idempotency_fingerprint, fingerprint)
                recovered_ids = await self._recover_expired_messages(db, message_id=row.id)
                if recovered_ids:
                    await db.refresh(row)
        self._sync_recovered_messages(recovered_ids)
        if row is None:
            return None
        message = self._local_message(str(row.id)) or _message_from_row(row)
        if message.status == 'streaming':
            self._track(message)
        return message

    async def create_with_message(self, owner: str, question: str, settings: dict,
                                  context: str, warnings: list[str], *, scope: str,
                                  key: str, fingerprint: str) -> Message:
        session_id = uuid.uuid4()
        message_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        message = Message(
            str(message_id), str(session_id), question, dict(settings), context, list(warnings),
            idempotency_owner=owner, idempotency_scope=scope, idempotency_key=key,
            idempotency_fingerprint=fingerprint,
        )
        try:
            async with session_scope() as db:
                db.add(ChatSessionRow(
                    id=session_id, owner=owner, title=question[:50], settings=dict(settings),
                    favorite=False, created_at=now, updated_at=now,
                ))
                db.add(ChatMessageRow(
                    id=message_id, session_id=session_id, question=question,
                    settings=dict(settings), attachment_context=context, warnings=list(warnings),
                    status='streaming', idempotency_owner=owner, idempotency_scope=scope,
                    idempotency_key=key, idempotency_fingerprint=fingerprint,
                    lease_expires_at=_lease_deadline(), created_at=now,
                ))
        except IntegrityError:
            existing = await self.find_idempotent_message(owner, scope, key, fingerprint)
            if existing is not None:
                return existing
            raise
        self._track(message)
        return message

    async def get(self, session_id: str, owner: str) -> Session:
        sid = uuid.UUID(session_id)
        recovered_ids: set[str] = set()
        async with session_scope() as db:
            found = await db.scalar(select(ChatSessionRow.id).where(
                ChatSessionRow.id == sid, ChatSessionRow.owner == owner,
            ))
            if found is None:
                row = None
            else:
                recovered_ids = await self._recover_expired_messages(db, session_id=sid)
                row = await db.scalar(
                    select(ChatSessionRow)
                    .where(ChatSessionRow.id == sid, ChatSessionRow.owner == owner)
                    .options(selectinload(ChatSessionRow.messages))
                )
        self._sync_recovered_messages(recovered_ids)
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
            # The generating message itself is always the in-memory object.
            messages = [tracked if item.id == message.id else item for item in messages]
        session = _session_from_row(row, messages)
        if not any(item is message for item in session.messages):
            if tracked is not None:
                session.messages = [tracked if item.id == message.id else item for item in session.messages]
            elif not any(item.id == message.id for item in session.messages):
                raise BusinessError(20004, '会话不存在或已过期', 404)
        return session

    async def message(self, message_id: str, owner: str) -> Message:
        cached = self.messages.get(message_id)
        if cached is not None:
            await self.get(cached.session_id, owner)
            if cached.task is None:
                # Keep one object per message on this worker, but never trust
                # its fields when another worker may have finished the row.
                async with get_session_factory()() as db:
                    row = await db.get(ChatMessageRow, uuid.UUID(message_id))
                if row is not None:
                    _sync_message_from_row(cached, row)
                if cached.status != 'streaming':
                    self._untrack(message_id)
            return cached
        mid = uuid.UUID(message_id)
        recovered_ids: set[str] = set()
        async with session_scope() as db:
            msg_owner = await db.scalar(
                select(ChatSessionRow.owner)
                .join(ChatMessageRow, ChatMessageRow.session_id == ChatSessionRow.id)
                .where(ChatMessageRow.id == mid)
            )
            if msg_owner == owner:
                recovered_ids = await self._recover_expired_messages(db, message_id=mid)
                msg_row = await db.get(ChatMessageRow, mid)
            else:
                msg_row = None
        self._sync_recovered_messages(recovered_ids)
        if msg_row is None:
            raise BusinessError(20004, '消息不存在或已过期', 404)
        message = _message_from_row(msg_row)
        # Track only runnable rows so this worker's stream/stop share one object;
        # terminal or remotely owned rows are re-read from the database next time.
        if message.status == 'streaming':
            self._track(message)
        else:
            self._untrack(message.id)
        return message

    async def add_message(self, session: Session, question: str, settings: dict,
                          context: str = '', warnings: list[str] | None = None, *,
                          idempotency_owner: str | None = None,
                          idempotency_scope: str | None = None,
                          idempotency_key: str | None = None,
                          idempotency_fingerprint: str | None = None) -> Message:
        sid = uuid.UUID(session.id)
        now = datetime.now(timezone.utc)
        message_id = uuid.uuid4()
        message = Message(
            str(message_id), session.id, question, dict(settings), context, warnings or [],
            idempotency_owner=idempotency_owner, idempotency_scope=idempotency_scope,
            idempotency_key=idempotency_key,
            idempotency_fingerprint=idempotency_fingerprint,
        )
        replay: Message | None = None
        recovered_ids: set[str] = set()
        try:
            async with session_scope() as db:
                session_row = await db.scalar(
                    select(ChatSessionRow)
                    .where(ChatSessionRow.id == sid, ChatSessionRow.owner == session.owner)
                    .with_for_update()
                )
                if session_row is None:
                    raise BusinessError(20004, '会话不存在或已过期', 404)
                recovered_ids = await self._recover_expired_messages(db, session_id=sid)
                if idempotency_key is not None:
                    existing_row = await db.scalar(select(ChatMessageRow).where(
                        ChatMessageRow.idempotency_owner == (idempotency_owner or session.owner),
                        ChatMessageRow.idempotency_scope == (idempotency_scope or ''),
                        ChatMessageRow.idempotency_key == idempotency_key,
                    ))
                    if existing_row is not None:
                        ensure_same_request(existing_row.idempotency_fingerprint,
                                            idempotency_fingerprint or '')
                        replay = (self._local_message(str(existing_row.id))
                                  or _message_from_row(existing_row))
                    else:
                        active = await db.scalar(select(exists().where(
                            ChatMessageRow.session_id == sid, ChatMessageRow.status == 'streaming',
                        )))
                        if active:
                            raise BusinessError(20009, '请先停止当前生成', 409)
                else:
                    active = await db.scalar(select(exists().where(
                        ChatMessageRow.session_id == sid, ChatMessageRow.status == 'streaming',
                    )))
                    if active:
                        raise BusinessError(20009, '请先停止当前生成', 409)

                if replay is None:
                    count = await db.scalar(select(func.count()).select_from(ChatMessageRow).where(
                        ChatMessageRow.session_id == sid,
                    ))
                    if int(count or 0) >= 100:
                        raise BusinessError(20009, '单个临时会话最多 100 轮，请新建会话', 429)
                    await db.execute(
                        update(ChatSessionRow).where(ChatSessionRow.id == sid)
                        .values(settings=dict(settings), updated_at=now)
                    )
                    db.add(ChatMessageRow(
                        id=message_id, session_id=sid, question=question, settings=dict(settings),
                        attachment_context=context, warnings=warnings or [], status='streaming',
                        idempotency_owner=idempotency_owner,
                        idempotency_scope=idempotency_scope,
                        idempotency_key=idempotency_key,
                        idempotency_fingerprint=idempotency_fingerprint,
                        lease_expires_at=_lease_deadline(), created_at=now,
                    ))
        except IntegrityError as error:
            if idempotency_key is not None:
                existing = await self.find_idempotent_message(
                    idempotency_owner or session.owner, idempotency_scope or '',
                    idempotency_key, idempotency_fingerprint or '',
                )
                if existing is not None:
                    return existing
            if _constraint_name(error) == 'uq_chat_messages_active':
                raise BusinessError(20009, '请先停止当前生成', 409) from None
            raise
        self._sync_recovered_messages(recovered_ids)
        if replay is not None:
            if replay.status == 'streaming':
                self._track(replay)
            return replay
        session.messages.append(message)
        session.settings = dict(settings)
        session.updated_at = _ts(now)
        self._track(message)
        return message

    async def claim_generation(self, message: Message, worker_id: str | None = None) -> bool:
        worker_id = worker_id or current_worker_id()
        async with session_scope() as db:
            claimed = await db.scalar(
                update(ChatMessageRow)
                .where(
                    ChatMessageRow.id == uuid.UUID(message.id),
                    ChatMessageRow.status == 'streaming',
                    ChatMessageRow.generation_claimed.is_(False),
                    ChatMessageRow.worker_id.is_(None),
                    # A runnable row carries a claim deadline; once it lapses the
                    # row is recovered as failed instead of starting late.
                    ChatMessageRow.lease_expires_at > func.clock_timestamp(),
                )
                .values(
                    generation_claimed=True,
                    worker_id=worker_id,
                    lease_expires_at=_lease_deadline(),
                )
                .returning(ChatMessageRow.lease_expires_at)
            )
        if claimed is None:
            await self.refresh_message(message)
            return False
        message.generation_claimed = True
        message.worker_id = worker_id
        message.lease_expires_at = claimed
        return True

    async def refresh_message(self, message: Message) -> None:
        """Mirror the durable row onto an object whose generation runs elsewhere."""
        recovered_ids: set[str] = set()
        async with session_scope() as db:
            recovered_ids = await self._recover_expired_messages(
                db, message_id=uuid.UUID(message.id),
            )
            row = await db.get(ChatMessageRow, uuid.UUID(message.id))
        self._sync_recovered_messages(recovered_ids)
        if row is None:
            return
        _sync_message_from_row(message, row)
        message.events.clear()
        if message.status != 'streaming':
            self._untrack(message.id)

    async def renew_generation(self, message_id: str, worker_id: str) -> bool | None:
        async with session_scope() as db:
            renewed = await db.scalar(
                update(ChatMessageRow)
                .where(
                    ChatMessageRow.id == uuid.UUID(message_id),
                    ChatMessageRow.status == 'streaming',
                    ChatMessageRow.worker_id == worker_id,
                    ChatMessageRow.lease_expires_at > func.clock_timestamp(),
                )
                .values(lease_expires_at=_lease_deadline())
                .returning(ChatMessageRow.id)
            )
            if renewed is not None:
                return True
            row = await db.scalar(select(ChatMessageRow).where(
                ChatMessageRow.id == uuid.UUID(message_id),
            ))
        if row is not None and row.status != 'streaming' and row.worker_id == worker_id:
            return None
        return False

    async def list(self, owner: str) -> list[dict]:
        async with get_session_factory()() as db:
            rows = await db.scalars(
                select(ChatSessionRow)
                .where(ChatSessionRow.owner == owner)
                .order_by(ChatSessionRow.favorite.desc(), ChatSessionRow.updated_at.desc())
            )
        sessions = [_session_from_row(row, []).public() for row in rows.all()]
        await self.touch_owner(owner)
        return sessions

    async def touch_owner(self, owner: str) -> None:
        """Renew the complete browser-local anonymous history after a successful read."""
        if not owner.startswith('anon:'):
            return
        async with session_scope() as db:
            await db.execute(
                update(ChatSessionRow)
                .where(ChatSessionRow.owner == owner)
                .values(updated_at=func.now())
            )

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
        await self.purge_owner_runtime(owner, {str(session_id) for session_id in rows})
        async with session_scope() as db:
            await db.execute(delete(ChatSessionRow).where(ChatSessionRow.owner == owner))

    async def purge_owner_runtime(self, owner: str, session_ids: set[str] | None = None) -> None:
        """Clear this worker's active messages and uploads without touching the database."""
        target_ids = session_ids or set()
        tasks = []
        for message_id, message in list(self.messages.items()):
            if message.session_id in target_ids:
                if message.task and not message.task.done():
                    message.task.cancel()
                    tasks.append(message.task)
                self._untrack(message_id)
        self.uploads = {
            key: value for key, value in self.uploads.items() if value['owner'] != owner
        }
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
        """Remove only terminal, expired anonymous sessions; message rows cascade."""
        streaming_exists = exists(
            select(ChatMessageRow.id).where(
                ChatMessageRow.session_id == ChatSessionRow.id,
                ChatMessageRow.status == 'streaming',
            )
        )
        async with session_scope() as db:
            deleted = await db.scalars(
                delete(ChatSessionRow)
                .where(
                    ChatSessionRow.owner.like('anon:%'),
                    ChatSessionRow.updated_at < cutoff,
                    ~streaming_exists,
                )
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
