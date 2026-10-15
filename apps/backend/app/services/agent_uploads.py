"""Temporary, owner-scoped Agent attachment text shared through PostgreSQL."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text, update

from app.core.database import chat_database_url, session_scope
from app.core.errors import BusinessError
from app.models.agent_upload import AgentUploadRow

UPLOAD_TTL_SECONDS = 86400
MAX_PENDING_PER_OWNER = 20
MISSING_UPLOAD = '附件不存在或已过期，请重新上传'


def _public(item: dict) -> dict:
    return {key: value for key, value in item.items()
            if key not in ('text', 'owner', 'expires_at')}


def _row_dict(row: AgentUploadRow) -> dict:
    return {
        'file_id': str(row.id), 'filename': row.filename, 'text': row.text,
        'owner': row.owner, 'original_length': row.original_length,
        'final_length': row.final_length, 'truncated': row.truncated,
        'warning': row.warning, 'parse_status': 'ok', 'expires_at': row.expires_at,
    }


class AgentUploadStore:
    def __init__(self) -> None:
        # Local development without CHAT_DATABASE_URL retains the existing ephemeral behavior.
        self._memory: dict[str, dict] = {}

    async def save(self, owner: str, filename: str, parsed: dict) -> dict:
        file_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=UPLOAD_TTL_SECONDS)
        filename = filename.replace('\\', '/').rsplit('/', 1)[-1][:500]
        if not chat_database_url():
            self._memory = {key: value for key, value in self._memory.items()
                            if value['expires_at'] > now}
            if sum(item['owner'] == owner for item in self._memory.values()) >= MAX_PENDING_PER_OWNER:
                raise BusinessError(20009, '待发送附件过多，请稍后重试', 429)
            item = {**parsed, 'file_id': str(file_id), 'filename': filename,
                    'owner': owner, 'expires_at': expires_at, 'parse_status': 'ok'}
            self._memory[str(file_id)] = item
            return _public(item)
        async with session_scope() as db:
            # One owner can upload from several devices at once; lock before the count.
            await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner, 1))'),
                             {'owner': owner})
            await db.execute(delete(AgentUploadRow).where(AgentUploadRow.expires_at <= now))
            count = await db.scalar(select(func.count(AgentUploadRow.id)).where(
                AgentUploadRow.owner == owner))
            if (count or 0) >= MAX_PENDING_PER_OWNER:
                raise BusinessError(20009, '待发送附件过多，请稍后重试', 429)
            row = AgentUploadRow(
                id=file_id, owner=owner, filename=filename, text=parsed['text'],
                original_length=parsed['original_length'], final_length=parsed['final_length'],
                truncated=parsed['truncated'], warning=parsed.get('warning'), expires_at=expires_at,
            )
            db.add(row)
        return _public(_row_dict(row))

    async def get_many(self, owner: str, file_ids: list[str]) -> dict[str, dict]:
        if not file_ids:
            return {}
        try:
            ids = [uuid.UUID(file_id) for file_id in file_ids]
        except (ValueError, TypeError) as exc:
            raise BusinessError(20004, MISSING_UPLOAD, 404) from exc
        now = datetime.now(timezone.utc)
        if not chat_database_url():
            found = {file_id: item for file_id in file_ids
                     if (item := self._memory.get(file_id)) and item['owner'] == owner
                     and item['expires_at'] > now}
        else:
            async with session_scope() as db:
                rows = (await db.scalars(select(AgentUploadRow).where(
                    AgentUploadRow.id.in_(ids), AgentUploadRow.owner == owner,
                    AgentUploadRow.expires_at > now))).all()
            found = {str(row.id): _row_dict(row) for row in rows}
        if any(file_id not in found for file_id in file_ids):
            raise BusinessError(20004, MISSING_UPLOAD, 404)
        return found

    async def get(self, owner: str, file_id: str) -> dict:
        return (await self.get_many(owner, [file_id]))[file_id]

    async def consume(self, owner: str, file_ids: list[str]) -> None:
        if not file_ids:
            return
        if not chat_database_url():
            for file_id in file_ids:
                if self._memory.get(file_id, {}).get('owner') == owner:
                    self._memory.pop(file_id, None)
            return
        ids = [uuid.UUID(file_id) for file_id in file_ids]
        async with session_scope() as db:
            await db.execute(delete(AgentUploadRow).where(
                AgentUploadRow.owner == owner, AgentUploadRow.id.in_(ids)))

    async def purge_owner(self, owner: str) -> None:
        self._memory = {key: item for key, item in self._memory.items() if item['owner'] != owner}
        if chat_database_url():
            async with session_scope() as db:
                await db.execute(delete(AgentUploadRow).where(AgentUploadRow.owner == owner))

    async def claim_owner(self, source: str, target: str) -> None:
        for item in self._memory.values():
            if item['owner'] == source:
                item['owner'] = target
        if chat_database_url():
            async with session_scope() as db:
                await db.execute(update(AgentUploadRow).where(
                    AgentUploadRow.owner == source, AgentUploadRow.expires_at > datetime.now(timezone.utc)
                ).values(owner=target))

    async def purge_expired(self) -> int:
        now = datetime.now(timezone.utc)
        if not chat_database_url():
            expired = [key for key, item in self._memory.items() if item['expires_at'] <= now]
            for key in expired:
                del self._memory[key]
            return len(expired)
        async with session_scope() as db:
            result = await db.execute(delete(AgentUploadRow).where(AgentUploadRow.expires_at <= now))
            return result.rowcount


agent_upload_store = AgentUploadStore()
