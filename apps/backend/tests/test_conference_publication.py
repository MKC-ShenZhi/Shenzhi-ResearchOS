"""Opt-in concurrency regressions, only an explicitly supplied disposable local audit DB."""

import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from app.core.database import dispose_engine, session_scope
from app.models.conference_snapshot import ConferenceSnapshotRow as Row
from app.models.interactions import ConferenceFollowRow
from app.services.conferences import ConferenceNotFoundError
from app.services.conferences.repository import (
    ConferenceSnapshotStore,
    PUBLISH_LOCK_KEY,
)
from app.services.library.conference_follows import ConferenceFollowService
from tests.test_conferences import snapshot, conference, edition

URL = os.getenv("SHENZHI_CONFERENCE_CONCURRENCY_TEST_URL", "")


@unittest.skipUnless(URL, "disposable local *_audit_test database required")
class PublicationRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_follow_and_publication_are_serialized_in_both_orders(self):
        url = make_url(URL)
        self.assertIn(url.host, ("127.0.0.1", "localhost", "::1"))
        self.assertTrue(url.database.endswith("_audit_test"))
        await dispose_engine()
        with patch.dict(os.environ, {"CHAT_DATABASE_URL": URL}):
            store = ConferenceSnapshotStore()
            follows = ConferenceFollowService()
            now = datetime.now(timezone.utc)
            original = snapshot(
                conference("ai-old", edition(2027, {"deadline": None})),
                conference("ai-keep", edition(2027, {"deadline": None})),
            )
            replacement = snapshot(
                conference("ai-keep", edition(2027, {"deadline": None}))
            )
            replacement["snapshot_id"] = "replacement"
            pending = None
            try:
                async with session_scope() as s:
                    self.assertEqual(
                        await s.scalar(select(func.count()).select_from(Row)),
                        0,
                        "Requires empty snapshot table",
                    )
                    self.assertEqual(
                        await s.scalar(
                            select(func.count()).select_from(ConferenceFollowRow)
                        ),
                        0,
                        "Requires empty follows table",
                    )
                await store.save(original, now)
                # Publication wins: a request with an old cached ID must fail after waiting.
                async with session_scope() as s:
                    await s.execute(
                        select(func.pg_advisory_xact_lock(PUBLISH_LOCK_KEY))
                    )
                    pending = asyncio.create_task(
                        follows.follow("audit-user", "ai-old")
                    )
                    with self.assertRaises(asyncio.TimeoutError):
                        await asyncio.wait_for(asyncio.shield(pending), 0.2)
                    await s.execute(
                        update(Row)
                        .where(Row.id == 1)
                        .values(payload=replacement, snapshot_id="replacement")
                    )
                with self.assertRaises(ConferenceNotFoundError):
                    await asyncio.wait_for(pending, 5)
                async with session_scope() as s:
                    self.assertEqual(
                        await s.scalar(
                            select(func.count()).select_from(ConferenceFollowRow)
                        ),
                        0,
                    )
                # Follow wins: a writer waiting on the lock must re-check new follows.
                await store.save(original, now)
                async with session_scope() as s:
                    await s.execute(
                        select(func.pg_advisory_xact_lock_shared(PUBLISH_LOCK_KEY))
                    )
                    s.add(
                        ConferenceFollowRow(
                            user_id="audit-user", conference_id="ai-old"
                        )
                    )
                    await s.flush()
                    pending = asyncio.create_task(store.save(replacement, now))
                    with self.assertRaises(asyncio.TimeoutError):
                        await asyncio.wait_for(asyncio.shield(pending), 0.2)
                await asyncio.wait_for(pending, 5)
                published = await store.payload()
                retained = next(item for item in published["conferences"] if item["id"] == "ai-old")
                self.assertTrue(retained["source_removed"])
                self.assertEqual(len(published["conferences"]), 2)
                with self.assertRaises(ConferenceNotFoundError):
                    await follows.follow("another-user", "ai-old")
                await follows.unfollow("audit-user", "ai-old")
                self.assertNotIn("ai-old", await follows.followed_ids("audit-user"))
                # Ordinary existing conference follows still work and stay idempotent.
                await follows.follow("audit-user", "ai-keep")
                await follows.follow("audit-user", "ai-keep")
                self.assertEqual(
                    await follows.followed_ids("audit-user"),
                    frozenset({"ai-keep"}),
                )
            finally:
                if pending and not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                await dispose_engine()
