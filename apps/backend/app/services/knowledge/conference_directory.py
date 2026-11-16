"""Refresh the paper library's shared directory outside the request path."""

import asyncio
import logging
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import database_url, dispose_engine, session_scope
from app.core.time import utc_now
from app.integrations.knowledge.adapter import KnowledgeAdapter
from app.models.knowledge_conference_snapshot import KnowledgeConferenceSnapshotRow as Snapshot
from app.schemas.knowledge import ConferenceListResponse


REFRESH_INTERVAL = timedelta(minutes=10)
STALE_AFTER = timedelta(hours=24)
REFRESH_TIMEOUT_SECONDS = 60
READ_TIMEOUT_SECONDS = 3
logger = logging.getLogger(__name__)


async def load_conference_directory() -> ConferenceListResponse | None:
    if database_url() is None:
        return None
    try:
        async with asyncio.timeout(READ_TIMEOUT_SECONDS), session_scope() as session:
            row = await session.get(Snapshot, 1)
            if row is None or row.updated_at is None:
                return None
            return ConferenceListResponse(
                items=row.items,
                snapshot_updated_at=row.updated_at,
                snapshot_stale=utc_now() - row.updated_at >= STALE_AFTER,
            )
    except (SQLAlchemyError, OSError, TimeoutError, ValidationError):
        logger.warning('Knowledge conference snapshot could not be read; using the live directory')
        return None


async def refresh_conference_directory() -> bool:
    if database_url() is None:
        return False
    started_at = utc_now()
    # Commit the claim before contacting upstream. All workers and the manual
    # command share the same ten-minute window, including after a failed fetch.
    claim = insert(Snapshot).values(id=1, attempted_at=started_at).on_conflict_do_update(
        index_elements=[Snapshot.id],
        set_={'attempted_at': started_at},
        where=Snapshot.attempted_at <= started_at - REFRESH_INTERVAL,
    ).returning(Snapshot.id)
    async with session_scope() as session:
        if await session.scalar(claim) is None:
            return False

    async with asyncio.timeout(REFRESH_TIMEOUT_SECONDS):
        directory = await KnowledgeAdapter().conferences()
    updated_at = utc_now()
    async with session_scope() as session:
        published = await session.scalar(
            update(Snapshot)
            .where(Snapshot.id == 1, Snapshot.attempted_at == started_at)
            .values(items=directory.model_dump(mode='json')['items'], updated_at=updated_at)
            .returning(Snapshot.id)
        )
    if published is None:
        return False
    logger.info('Knowledge conference directory refreshed: items=%d', len(directory.items))
    return True


async def _sync_once() -> None:
    try:
        await refresh_conference_directory()
        directory = await load_conference_directory()
        if directory is None or directory.snapshot_stale:
            raise SystemExit('No current knowledge conference directory is available. Retry after the next sync window.')
        print(f'Knowledge conference directory ready: {len(directory.items)} items, updated {directory.snapshot_updated_at}')
    finally:
        await dispose_engine()


if __name__ == '__main__':
    asyncio.run(_sync_once())
