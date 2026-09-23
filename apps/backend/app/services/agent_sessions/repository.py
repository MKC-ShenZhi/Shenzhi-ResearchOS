"""Agent session repository: memory fallback or PostgreSQL when configured."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from typing import Any, Protocol

from app.core.errors import BusinessError
from app.services.agent_sessions.entities import AgentSession, AgentTurn

__all__ = [
    'AgentSession', 'AgentTurn', 'AgentSessionRepository', 'MemoryAgentSessionRepository',
    'agent_session_repository', 'decode_cursor', 'encode_cursor',
]


def new_session_id() -> str:
    return f'ses_{uuid.uuid4().hex}'


def new_turn_id() -> str:
    return f'turn_{uuid.uuid4().hex}'


def encode_cursor(updated_at: float, session_id: str) -> str:
    raw = json.dumps([updated_at, session_id], separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_cursor(cursor: str | None) -> tuple[float, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + '=' * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        if (not isinstance(value, list) or len(value) != 2
                or not isinstance(value[0], (int, float)) or not isinstance(value[1], str)):
            raise ValueError
        return float(value[0]), value[1]
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise BusinessError(20001, '无效的会话分页游标') from None


class AgentSessionRepository(Protocol):
    is_durable: bool

    async def recover(self) -> None: ...
    async def create(self, owner: str, prompt: str, settings: dict,
                     branched_from: str | None = None) -> AgentSession: ...
    async def get(self, session_id: str, owner: str) -> AgentSession: ...
    async def list_page(self, owner: str, limit: int, cursor: str | None) -> dict: ...
    async def update_title(self, session_id: str, owner: str, title: str) -> AgentSession: ...
    async def delete(self, session_id: str, owner: str) -> None: ...
    async def start_turn(self, session_id: str, owner: str, prompt: str,
                         settings: dict, warnings: list[str]) -> AgentTurn: ...
    async def finish_turn(self, session_id: str, owner: str, turn_id: str,
                          payload: dict[str, Any]) -> AgentTurn: ...
    async def import_legacy(self, owner: str, payload: dict[str, Any]) -> AgentSession: ...
    async def claim_anonymous_sessions(self, source_owner: str, target_owner: str) -> dict: ...
    async def purge_owner(self, owner: str) -> int: ...
    async def close(self) -> None: ...


class MemoryAgentSessionRepository:
    is_durable = False

    def __init__(self, max_sessions: int = 500):
        self.sessions: dict[str, AgentSession] = {}
        self.max_sessions = max_sessions
        self._lock = asyncio.Lock()

    async def recover(self) -> None:
        return None

    async def create(self, owner: str, prompt: str, settings: dict,
                     branched_from: str | None = None) -> AgentSession:
        async with self._lock:
            if len(self.sessions) >= self.max_sessions:
                raise BusinessError(20009, '临时会话容量已满，请删除旧会话', 429)
            now = time.time()
            session = AgentSession(
                id=new_session_id(), owner=owner, title=(prompt.strip()[:50] or '新会话'),
                settings=dict(settings), branched_from=branched_from,
                created_at=now, updated_at=now,
            )
            self.sessions[session.id] = session
            return session

    async def get(self, session_id: str, owner: str) -> AgentSession:
        session = self.sessions.get(session_id)
        if session is None or session.owner != owner:
            raise BusinessError(20004, 'Agent 会话不存在或无权访问', 404)
        return session

    async def list_page(self, owner: str, limit: int, cursor: str | None) -> dict:
        boundary = decode_cursor(cursor)
        items = sorted(
            (session for session in self.sessions.values() if session.owner == owner),
            key=lambda item: (item.updated_at, item.id), reverse=True,
        )
        if boundary:
            items = [item for item in items if (item.updated_at, item.id) < boundary]
        page = items[:limit]
        has_more = len(items) > limit
        return {
            'sessions': [item.summary() for item in page],
            'next_cursor': encode_cursor(page[-1].updated_at, page[-1].id) if has_more and page else None,
            'has_more': has_more,
        }

    async def update_title(self, session_id: str, owner: str, title: str) -> AgentSession:
        session = await self.get(session_id, owner)
        value = title.strip()
        if not value:
            raise BusinessError(20001, '会话名称不能为空')
        session.title = value
        session.updated_at = time.time()
        return session

    async def delete(self, session_id: str, owner: str) -> None:
        async with self._lock:
            session = await self.get(session_id, owner)
            if any(turn.status == 'running' for turn in session.turns):
                raise BusinessError(20009, '请先停止当前 Agent 运行', 409)
            del self.sessions[session_id]

    async def start_turn(self, session_id: str, owner: str, prompt: str,
                         settings: dict, warnings: list[str]) -> AgentTurn:
        async with self._lock:
            session = await self.get(session_id, owner)
            if any(turn.status == 'running' for turn in session.turns):
                raise BusinessError(20009, '该会话已有正在运行的任务', 409)
            turn = AgentTurn(new_turn_id(), session.id, prompt, dict(settings), warnings=list(warnings))
            session.turns.append(turn)
            session.settings = dict(settings)
            session.updated_at = time.time()
            return turn

    async def finish_turn(self, session_id: str, owner: str, turn_id: str,
                          payload: dict[str, Any]) -> AgentTurn:
        async with self._lock:
            session = await self.get(session_id, owner)
            turn = next((item for item in session.turns if item.id == turn_id), None)
            if turn is None or turn.status != 'running':
                raise BusinessError(20004, 'Agent 轮次不存在或已经结束', 404)
            for key, value in payload.items():
                if hasattr(turn, key):
                    setattr(turn, key, value)
            turn.completed_at = turn.completed_at or time.time()
            session.updated_at = turn.completed_at
            return turn

    async def import_legacy(self, owner: str, payload: dict[str, Any]) -> AgentSession:
        import_key = str(payload['import_key'])
        existing = next((item for item in self.sessions.values()
                         if item.owner == owner and item.import_key == import_key), None)
        if existing:
            return existing
        session = await self.create(owner, str(payload.get('title') or '本地会话'), {},
                                    payload.get('branched_from'))
        session.import_key = import_key
        session.created_at = float(payload.get('created_at') or session.created_at)
        session.updated_at = float(payload.get('updated_at') or session.updated_at)
        _populate_legacy_turns(session, payload.get('turns') or [])
        return session

    async def claim_anonymous_sessions(self, source_owner: str, target_owner: str) -> dict:
        # Memory mode cannot promise a durable ownership migration.
        return {'moved_count': 0, 'skipped_running_count': 0, 'durable': False}

    async def purge_owner(self, owner: str) -> int:
        ids = [item.id for item in self.sessions.values() if item.owner == owner]
        for session_id in ids:
            self.sessions.pop(session_id, None)
        return len(ids)

    async def close(self) -> None:
        return None


def _populate_legacy_turns(session: AgentSession, raw_turns: list[dict[str, Any]]) -> None:
    """Convert localStorage message pairs into persisted product turns and safe runtime history."""
    history: list[dict[str, Any]] = []
    pending_user: dict[str, Any] | None = None
    for raw in raw_turns:
        if raw.get('role') == 'user':
            pending_user = raw
            continue
        if raw.get('role') != 'assistant' or pending_user is None:
            continue
        user_content = str(pending_user.get('content') or '')
        assistant_content = str(raw.get('content') or '')
        history.extend([
            {'kind': 'user', 'text': user_content},
            {'kind': 'assistant', 'content': str(raw.get('report') or assistant_content),
             'reasoning': str(raw.get('reasoning') or ''), 'tool_calls': [], 'stop_reason': 'stop',
             'usage_tokens': 0},
        ])
        sequence_time = session.created_at + len(session.turns) / 1_000_000
        turn = AgentTurn(
            id=new_turn_id(), session_id=session.id, user_content=user_content, settings={},
            assistant_content=assistant_content, reasoning=str(raw.get('reasoning') or ''),
            process=list(raw.get('process') or []), steers=list(raw.get('steers') or []),
            report=raw.get('report'), sources=list(raw.get('sources') or []),
            question=raw.get('question'), warnings=list(raw.get('warnings') or []),
            error=raw.get('error'), stopped=bool(raw.get('stopped')),
            stop_reason=raw.get('stopReason'), status='stopped' if raw.get('stopped') else 'done',
            transcript=list(history), created_at=sequence_time,
            completed_at=max(sequence_time, session.updated_at),
        )
        session.turns.append(turn)
        pending_user = None


def build_agent_session_repository() -> AgentSessionRepository:
    if os.getenv('CHAT_DATABASE_URL', '').strip():
        from app.services.agent_sessions.postgres_repository import PostgresAgentSessionRepository
        return PostgresAgentSessionRepository()
    return MemoryAgentSessionRepository()


agent_session_repository: AgentSessionRepository = build_agent_session_repository()
