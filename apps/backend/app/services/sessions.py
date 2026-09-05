"""Session repository: in-memory (default) or PostgreSQL when CHAT_DATABASE_URL is set."""
import asyncio
import os
import time
import uuid
from datetime import datetime
from typing import Protocol

from app.core.errors import BusinessError
from app.services.session_entities import Message, Session

__all__ = ['Message', 'Session', 'SessionRepository', 'MemorySessionRepository',
           'build_repository', 'repository']


class SessionRepository(Protocol):
    is_durable: bool

    async def recover(self) -> None: ...
    async def persist_message(self, message: Message) -> None: ...
    async def create(self, owner: str, question: str, settings: dict) -> Session: ...
    async def get(self, session_id: str, owner: str) -> Session: ...
    async def session_for_message(self, message: Message) -> Session: ...
    async def message(self, message_id: str, owner: str) -> Message: ...
    async def add_message(self, session: Session, question: str, settings: dict,
                          context: str = '', warnings: list[str] | None = None) -> Message: ...
    async def list(self, owner: str) -> list[dict]: ...
    async def update(self, session_id: str, owner: str, *, title: str | None = None,
                     favorite: bool | None = None) -> Session: ...
    async def touch(self, session_id: str) -> None: ...
    async def clear(self) -> None: ...
    async def purge_owner(self, owner: str) -> None: ...
    async def delete(self, session_id: str, owner: str) -> None: ...
    async def claim_anonymous_sessions(self, source_owner: str, target_owner: str) -> dict: ...
    async def purge_expired_anonymous_sessions(self, cutoff: datetime) -> int: ...
    def prune(self) -> None: ...
    def save_upload(self, owner: str, filename: str, parsed: dict) -> dict: ...
    def upload(self, file_id: str, owner: str) -> dict: ...
    async def close(self) -> None: ...


class MemorySessionRepository:
    is_durable = False

    def __init__(self, max_sessions: int = 500, ttl: float = 86400):
        self.sessions: dict[str, Session] = {}
        self.messages: dict[str, Message] = {}
        self.uploads: dict[str, dict] = {}
        self.max_sessions = max_sessions
        self.ttl = ttl

    async def recover(self) -> None:
        return None

    async def persist_message(self, message: Message) -> None:
        return None

    def _prune(self) -> None:
        cutoff = time.time() - self.ttl
        for session in list(self.sessions.values()):
            if session.updated_at < cutoff and not any(item.task and not item.task.done() for item in session.messages):
                self._delete(session.id, session.owner)
        self.uploads = {key: value for key, value in self.uploads.items() if value['created_at'] > cutoff}

    async def create(self, owner: str, question: str, settings: dict) -> Session:
        self._prune()
        if len(self.sessions) >= self.max_sessions:
            raise BusinessError(20009, '临时会话容量已满，请删除旧会话', 429)
        session = Session(str(uuid.uuid4()), owner, question[:50], settings)
        self.sessions[session.id] = session
        return session

    async def get(self, session_id: str, owner: str) -> Session:
        session = self.sessions.get(session_id)
        if not session or session.owner != owner:
            raise BusinessError(20004, '会话不存在或已过期', 404)
        return session

    async def session_for_message(self, message: Message) -> Session:
        session = self.sessions.get(message.session_id)
        if not session or not any(item is message for item in session.messages):
            raise BusinessError(20004, '会话不存在或已过期', 404)
        return session

    async def message(self, message_id: str, owner: str) -> Message:
        message = self.messages.get(message_id)
        if not message:
            raise BusinessError(20004, '消息不存在或已过期', 404)
        await self.get(message.session_id, owner)
        return message

    async def add_message(self, session: Session, question: str, settings: dict,
                          context: str = '', warnings: list[str] | None = None) -> Message:
        if any(item.status == 'streaming' for item in session.messages):
            raise BusinessError(20009, '请先停止当前生成', 409)
        if len(session.messages) >= 100:
            raise BusinessError(20009, '单个临时会话最多 100 轮，请新建会话', 429)
        message = Message(str(uuid.uuid4()), session.id, question, dict(settings), context, warnings or [])
        session.messages.append(message)
        session.settings = dict(settings)
        session.updated_at = time.time()
        self.messages[message.id] = message
        return message

    async def list(self, owner: str) -> list[dict]:
        self._prune()
        return [item.public() for item in sorted(self.sessions.values(),
                key=lambda session: (session.favorite, session.updated_at), reverse=True) if item.owner == owner]

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
        return session

    async def touch(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session:
            session.updated_at = time.time()

    async def clear(self) -> None:
        self.sessions.clear()
        self.messages.clear()
        self.uploads.clear()

    async def purge_owner(self, owner: str) -> None:
        for session in [item for item in self.sessions.values() if item.owner == owner]:
            self._delete(session.id, owner)

    async def delete(self, session_id: str, owner: str) -> None:
        self._delete(session_id, owner)

    async def claim_anonymous_sessions(self, source_owner: str, target_owner: str) -> dict:
        """Memory mode must never claim that an ephemeral ownership change is durable."""
        return {'moved_count': 0, 'skipped_streaming_count': 0, 'durable': False}

    async def purge_expired_anonymous_sessions(self, cutoff: datetime) -> int:
        # Memory mode is process-local and already prunes its own short-lived cache.
        return 0

    def _delete(self, session_id: str, owner: str) -> None:
        session = self.sessions.get(session_id)
        if not session or session.owner != owner:
            raise BusinessError(20004, '会话不存在或已过期', 404)
        for message in session.messages:
            if message.task and not message.task.done():
                message.task.cancel()
            self.messages.pop(message.id, None)
        del self.sessions[session_id]

    def prune(self) -> None:
        self._prune()

    def save_upload(self, owner: str, filename: str, parsed: dict) -> dict:
        self._prune()
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


def build_repository() -> SessionRepository:
    if os.getenv('CHAT_DATABASE_URL', '').strip():
        from app.services.postgres_sessions import PostgresSessionRepository
        return PostgresSessionRepository()
    return MemorySessionRepository()


repository: SessionRepository = build_repository()
