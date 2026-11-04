"""Async snapshot persistence and bounded per-process catalog cache."""

from __future__ import annotations
import asyncio
import logging
import time
from sqlalchemy import select, update, func
from sqlalchemy.orm import defer
from sqlalchemy.dialects.postgresql import insert
from app.core.database import chat_database_url, session_scope
from app.models.conference_snapshot import ConferenceSnapshotRow as Row
from app.models.interactions import ConferenceFollowRow
from app.schemas.conferences import ConferenceSnapshotFile
from app.services.conferences import catalog_from_snapshot, load_conference_catalog

logger = logging.getLogger(__name__)
# Short transaction lock shared with follow writes; never held while downloading.
PUBLISH_LOCK_KEY = 7_402_118_033


class ConferenceSnapshotStore:
    async def state(self):
        async with session_scope() as session:
            return await session.scalar(
                select(Row).options(defer(Row.payload)).where(Row.id == 1)
            )

    async def version(self):
        async with session_scope() as session:
            return await session.scalar(select(Row.snapshot_id).where(Row.id == 1))

    async def payload(self):
        async with session_scope() as session:
            return await session.scalar(select(Row.payload).where(Row.id == 1))

    async def attempt(self, now):
        async with session_scope() as session:
            await session.execute(
                insert(Row)
                .values(id=1, attempted_at=now)
                .on_conflict_do_update(
                    index_elements=["id"], set_={"attempted_at": now}
                )
            )

    async def checked(self, now):
        async with session_scope() as session:
            await session.execute(update(Row).where(Row.id == 1).values(checked_at=now))

    async def followed_ids(self):
        async with session_scope() as session:
            return set(
                await session.scalars(
                    select(ConferenceFollowRow.conference_id).distinct()
                )
            )

    async def save(self, snapshot: dict, now):
        model = ConferenceSnapshotFile.model_validate(snapshot)
        values = dict(
            payload=snapshot,
            snapshot_id=model.snapshot_id,
            upstream_sha=model.source.revision,
            data_as_of=model.data_as_of,
            synced_at=now,
            checked_at=now,
            attempted_at=now,
        )
        async with session_scope() as session:
            await session.execute(select(func.pg_advisory_xact_lock(PUBLISH_LOCK_KEY)))
            # Recheck under the same lock used by follow writes. The earlier
            # orchestration check alone races with a user's new follow.
            followed = set(
                await session.scalars(
                    select(ConferenceFollowRow.conference_id).distinct()
                )
            )
            missing = followed - {item.id for item in model.conferences}
            if missing:
                raise ValueError(f"Followed conference IDs missing: {sorted(missing)}")
            await session.execute(
                insert(Row)
                .values(id=1, **values)
                .on_conflict_do_update(index_elements=["id"], set_=values)
            )


class ConferenceCatalogCache:
    """Check a tiny version column every 5 minutes; parse payload only when changed.

    Single-flight refresh prevents concurrent requests stampeding the database.
    On DB failure keep the last validated catalog, or the packaged fallback.
    """

    def __init__(self, store=None, clock=time.monotonic, ttl=300):
        self.store = store or ConferenceSnapshotStore()
        self.clock, self.ttl = clock, ttl
        self.catalog = None
        self.version = None
        self.expires = 0.0
        self.lock = asyncio.Lock()

    async def get(self):
        if not chat_database_url():
            return load_conference_catalog()
        if self.catalog is not None and self.clock() < self.expires:
            return self.catalog
        async with self.lock:
            if self.catalog is not None and self.clock() < self.expires:
                return self.catalog
            try:
                async with asyncio.timeout(3):
                    version = await self.store.version()
                if version and (version != self.version or self.catalog is None):
                    async with asyncio.timeout(3):
                        payload = await self.store.payload()
                    if payload is None:
                        raise ValueError("Snapshot version has no payload")
                    model = ConferenceSnapshotFile.model_validate(payload)
                    candidate = await asyncio.to_thread(catalog_from_snapshot, model)
                    self.catalog, self.version = candidate, model.snapshot_id
                elif not version:
                    self.catalog, self.version = load_conference_catalog(), None
            except Exception:
                logger.exception(
                    "Conference snapshot refresh failed; keeping last valid catalog"
                )
            if self.catalog is None:
                self.catalog = load_conference_catalog()
            self.expires = self.clock() + self.ttl
            return self.catalog


conference_catalog_cache = ConferenceCatalogCache()
