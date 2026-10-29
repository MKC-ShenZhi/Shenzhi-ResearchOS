"""Live PostgreSQL acceptance for atomic daily snapshots and the read contract."""

import os
import unittest
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete, func, select

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.collections import CollectionFolderRow, CollectionItemRow, CollectionUserStateRow
from app.models.interactions import PaperLikeRow, TopicFollowRow
from app.models.stats import PaperStatDailyRow, StatsSnapshotRunRow, TopicStatDailyRow
from app.services.library.collections import CollectionService
from app.services.library.paper_likes import PaperLikeService
from app.services.library.topic_follows import TopicFollowService
from app.services.stats.service import PlatformStatsService
from app.services.stats.snapshot import SNAPSHOT_VERSION, SnapshotService


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class SnapshotPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import dispose_engine

        await dispose_engine()
        self.user_a = f'snapshot-a-{uuid.uuid4()}'
        self.user_b = f'snapshot-b-{uuid.uuid4()}'
        self.paper_id = f'paper:snapshot:{uuid.uuid4()}'
        self.absent_paper_id = f'paper:absent:{uuid.uuid4()}'
        self.topic_id = 'deep-learning'
        self.day = date(2001, 1, 1) + timedelta(days=uuid.uuid4().int % 7000)
        self.unpublished_day = date(1990, 1, 1) + timedelta(days=uuid.uuid4().int % 300)
        self.service = PlatformStatsService()
        await self._cleanup()

    async def asyncTearDown(self):
        await self._cleanup()
        from app.core.database import dispose_engine

        await dispose_engine()

    async def _cleanup(self):
        async with session_scope() as db:
            for day in (self.day, self.unpublished_day):
                await db.execute(delete(StatsSnapshotRunRow).where(StatsSnapshotRunRow.snapshot_date == day))
            folder_ids = select(CollectionFolderRow.id).where(
                CollectionFolderRow.user_id.in_([self.user_a, self.user_b]),
            )
            await db.execute(delete(CollectionItemRow).where(CollectionItemRow.folder_id.in_(folder_ids)))
            await db.execute(delete(CollectionFolderRow).where(
                CollectionFolderRow.user_id.in_([self.user_a, self.user_b]),
            ))
            await db.execute(delete(CollectionUserStateRow).where(
                CollectionUserStateRow.user_id.in_([self.user_a, self.user_b]),
            ))
            await db.execute(delete(PaperLikeRow).where(PaperLikeRow.user_id.in_([self.user_a, self.user_b])))
            await db.execute(delete(TopicFollowRow).where(
                TopicFollowRow.user_id.in_([self.user_a, self.user_b]),
            ))

    async def _seed(self) -> None:
        collections = CollectionService()
        folders_a = (await collections.folders(self.user_a)).folders
        folders_b = (await collections.folders(self.user_b)).folders
        await collections.update_paper_folders(
            self.user_a, self.paper_id, [folders_a[0].id, folders_a[1].id],
        )
        await collections.update_paper_folders(self.user_b, self.paper_id, [folders_b[0].id])
        likes = PaperLikeService()
        await likes.like(self.user_a, self.paper_id)
        await likes.like(self.user_b, self.paper_id)
        follows = TopicFollowService()
        await follows.follow(self.user_a, self.topic_id)
        await follows.follow(self.user_b, self.topic_id)

    async def test_snapshot_records_distinct_counts_for_the_whole_catalog(self):
        await self._seed()

        result = await SnapshotService().build(self.day)
        self.assertEqual(result.snapshot_date, self.day)
        self.assertEqual(result.snapshot_version, SNAPSHOT_VERSION)
        self.assertEqual(result.topic_count, 293)
        self.assertGreaterEqual(result.paper_count, 1)

        page = await self.service.papers_page(snapshot_date=self.day, limit=500)
        self.assertEqual(page.snapshot_date, self.day)
        self.assertEqual(page.snapshot_version, SNAPSHOT_VERSION)
        rows = {item.paper_id: item for item in page.items}
        self.assertEqual(rows[self.paper_id].collector_count, 2)
        self.assertEqual(rows[self.paper_id].like_count, 2)

        topics = await self.service.topics_page(snapshot_date=self.day, limit=500)
        self.assertEqual(len(topics.items), 293)
        self.assertEqual({item.topic_id: item.follower_count for item in topics.items}[self.topic_id], 2)

        meta = await self.service.meta()
        self.assertTrue(meta.published)
        self.assertIsNotNone(meta.computed_at)
        self.assertEqual(meta.snapshot_version, SNAPSHOT_VERSION)

    async def test_same_day_rebuild_replaces_rows_without_duplicates(self):
        await self._seed()
        await SnapshotService().build(self.day)
        await TopicFollowService().unfollow(self.user_b, self.topic_id)

        await SnapshotService().build(self.day)

        async with session_scope() as db:
            self.assertEqual(await db.scalar(
                select(func.count()).select_from(PaperStatDailyRow).where(
                    PaperStatDailyRow.snapshot_date == self.day,
                    PaperStatDailyRow.paper_id == self.paper_id,
                )
            ), 1)
            self.assertEqual(await db.scalar(
                select(func.count()).select_from(TopicStatDailyRow).where(
                    TopicStatDailyRow.snapshot_date == self.day,
                    TopicStatDailyRow.topic_id == self.topic_id,
                )
            ), 1)

        topics = await self.service.topics_page(snapshot_date=self.day, limit=500)
        self.assertEqual({item.topic_id: item.follower_count for item in topics.items}[self.topic_id], 1)

    async def test_failed_rebuild_keeps_the_previous_complete_publication(self):
        await self._seed()
        await SnapshotService().build(self.day)

        with patch(
            'app.services.stats.snapshot.SnapshotService._like_counts',
            new=AsyncMock(side_effect=RuntimeError('boom')),
        ):
            with self.assertRaises(RuntimeError):
                await SnapshotService().build(self.day)

        async with session_scope() as db:
            run = await db.get(StatsSnapshotRunRow, self.day)
            self.assertIsNotNone(run)
            self.assertEqual(run.status, 'completed')
            self.assertEqual(run.failure_reason, 'RuntimeError')

        page = await self.service.papers_page(snapshot_date=self.day, limit=500)
        rows = {item.paper_id: item for item in page.items}
        self.assertEqual(rows[self.paper_id].collector_count, 2)
        self.assertEqual(rows[self.paper_id].like_count, 2)

    async def test_failed_first_build_is_not_published(self):
        with patch(
            'app.services.stats.snapshot.SnapshotService._like_counts',
            new=AsyncMock(side_effect=RuntimeError('boom')),
        ):
            with self.assertRaises(RuntimeError):
                await SnapshotService().build(self.unpublished_day)

        async with session_scope() as db:
            run = await db.get(StatsSnapshotRunRow, self.unpublished_day)
            self.assertIsNotNone(run)
            self.assertEqual(run.status, 'failed')
            self.assertIsNone(run.computed_at)

        with self.assertRaises(BusinessError) as caught:
            await self.service.papers_page(snapshot_date=self.unpublished_day, limit=10)
        self.assertEqual(caught.exception.status, 404)

    async def test_pagination_and_explicit_lookup(self):
        await self._seed()
        await SnapshotService().build(self.day)

        first = await self.service.papers_page(snapshot_date=self.day, limit=1)
        self.assertTrue(first.has_more)
        self.assertIsNotNone(first.next_cursor)
        second = await self.service.papers_page(snapshot_date=self.day, limit=1, cursor=first.next_cursor)
        self.assertNotEqual(first.items[0].paper_id, second.items[0].paper_id)

        lookup = await self.service.papers_page(
            snapshot_date=self.day, limit=10, paper_ids=[self.paper_id, self.absent_paper_id],
        )
        self.assertEqual([item.paper_id for item in lookup.items], [self.paper_id])
        self.assertEqual(lookup.missing_paper_ids, [self.absent_paper_id])
        self.assertIsNone(lookup.next_cursor)

        with self.assertRaises(BusinessError):
            await self.service.papers_page(
                snapshot_date=self.day, limit=10, paper_ids=[self.paper_id], cursor=first.next_cursor,
            )
        with self.assertRaises(BusinessError):
            await self.service.papers_page(snapshot_date=None, limit=10, cursor='not-a-cursor')
        with self.assertRaises(BusinessError):
            await self.service.topics_page(snapshot_date=self.unpublished_day, limit=10)


if __name__ == '__main__':
    unittest.main()
