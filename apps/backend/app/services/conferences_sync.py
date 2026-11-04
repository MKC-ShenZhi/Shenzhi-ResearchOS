"""Daily guarded upstream sync. CLI and scheduler share the same advisory lock."""

from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
from sqlalchemy import func, select
from app.core.database import session_scope
from app.core.time import utc_now
from app.integrations.conferences.client import ConferenceGitHubClient
from app.services.conferences import load_conference_catalog, catalog_from_snapshot
from app.schemas.conferences import ConferenceSnapshotFile
from app.services.conferences_repository import ConferenceSnapshotStore
from app.services.conferences_source import snapshot_from_files

logger = logging.getLogger(__name__)
LOCK_KEY = 7_402_118_032
# Reserve time for hourly trigger jitter, download and catalog refresh.
SYNC_INTERVAL = timedelta(hours=22)


def validate_replacement(snapshot, previous, followed):
    catalog_from_snapshot(ConferenceSnapshotFile.model_validate(snapshot))
    old_ids = {c["id"] for c in previous["conferences"]}
    new_ids = {c["id"] for c in snapshot["conferences"]}
    if len(new_ids) < len(old_ids) * 0.9:
        raise ValueError("Conference count shrank by more than 10%")
    removed = sorted(old_ids - new_ids)
    if removed:
        logger.warning("Conference IDs removed: %s", removed)
    missing = sorted(set(followed) - new_ids)
    if missing:
        raise ValueError(f"Followed conference IDs missing: {missing}")
    return removed


class ConferenceSync:
    def __init__(self, store=None, client=None):
        self.store = store or ConferenceSnapshotStore()
        self.client = client or ConferenceGitHubClient()

    async def run(self, *, dry_run=False, force=False, now=None):
        # Both scheduled and manual writers serialize, including due checks.
        async with session_scope() as lock_session:
            if not await lock_session.scalar(
                select(func.pg_try_advisory_xact_lock(LOCK_KEY))
            ):
                return {"status": "locked"}
            return await self.sync(dry_run=dry_run, force=force, now=now)

    async def sync(self, *, dry_run=False, force=False, now=None):
        now = now or utc_now()
        state = await self.store.state()
        if not force and state:
            if state.attempted_at and (
                not state.checked_at or state.attempted_at > state.checked_at
            ):
                if now - state.attempted_at < timedelta(hours=1):
                    return {"status": "retry-delayed"}
            elif state.checked_at and now - state.checked_at < SYNC_INTERVAL:
                return {"status": "not-due"}
        if not dry_run:
            # Durable even when network/validation fails or this process is restarted.
            await self.store.attempt(now)
        sha, commit_date = await self.client.latest()
        if state and state.snapshot_id and state.upstream_sha == sha:
            if not dry_run:
                await self.store.checked(now)
            return {"status": "unchanged", "sha": sha}
        async with asyncio.timeout(180):
            files = await self.client.download(sha)
        snapshot = await asyncio.to_thread(snapshot_from_files, files, sha, commit_date)
        previous = await self.store.payload() if state and state.snapshot_id else None
        if previous is None:
            previous = load_conference_catalog().snapshot.model_dump(mode="json")
        followed = await self.store.followed_ids()
        removed = await asyncio.to_thread(validate_replacement, snapshot, previous, followed)
        result = {
            "status": "dry-run" if dry_run else "updated",
            "sha": sha,
            "snapshot_id": snapshot["snapshot_id"],
            "conferences": len(snapshot["conferences"]),
            "removed_ids": removed,
        }
        if not dry_run:
            await self.store.save(snapshot, now)
        logger.info("Conference sync: %s", result)
        return result
