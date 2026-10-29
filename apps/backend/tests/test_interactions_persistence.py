"""Live PostgreSQL acceptance for distinct-user counters and idempotent writes."""

import asyncio
import os
import unittest
import uuid
from unittest.mock import AsyncMock

from sqlalchemy import delete, select

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.collections import CollectionFolderRow, CollectionItemRow, CollectionUserStateRow
from app.models.interactions import PaperLikeRow, TopicFollowRow
from app.services.library.collections import CollectionService
from app.services.library.paper_likes import PaperLikeService
from app.services.library.topic_follows import TopicFollowService
from app.schemas.knowledge import PaperSummary, Provenance
from app.services.user.account_deletion import AccountDeletionService


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class InteractionPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import dispose_engine

        await dispose_engine()
        self.user_a = f'interaction-a-{uuid.uuid4()}'
        self.user_b = f'interaction-b-{uuid.uuid4()}'
        self.paper_id = f'paper:count:{uuid.uuid4()}'
        self.like_paper_id = f'paper:like:{uuid.uuid4()}'
        self.topic_id = 'deep-learning'
        await self._cleanup()

    async def asyncTearDown(self):
        await self._cleanup()
        from app.core.database import dispose_engine

        await dispose_engine()

    async def _cleanup(self):
        async with session_scope() as db:
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

    async def test_collector_count_deduplicates_users_across_folders(self):
        collections = CollectionService()
        folders = (await collections.folders(self.user_a)).folders
        self.assertEqual(len(folders), 3)
        folder_ids = [folder.id for folder in folders]

        # One user holding the same paper in three folders counts once.
        await collections.update_paper_folders(self.user_a, self.paper_id, folder_ids)
        collections.knowledge.batch_get_papers = AsyncMock(return_value=[
            PaperSummary(id=self.paper_id, title='Collected paper', provenance=Provenance(external_id=self.paper_id)),
        ])
        collected = await collections.collected_papers(self.user_a, 1, 20)
        self.assertEqual((collected.total, [item.paper_id for item in collected.items]), (1, [self.paper_id]))
        self.assertEqual(await collections.collector_counts([self.paper_id]), {self.paper_id: 1})
        self.assertEqual(
            await collections.paper_folder_map(self.user_a, [self.paper_id]),
            {self.paper_id: sorted(folder_ids)},
        )

        second_user_folder = (await collections.folders(self.user_b)).folders[0].id
        await collections.update_paper_folders(self.user_b, self.paper_id, [second_user_folder])
        self.assertEqual(await collections.collector_counts([self.paper_id]), {self.paper_id: 2})

        # Removing one of several folders keeps the distinct-user count unchanged.
        await collections.remove_paper(self.user_a, folder_ids[0], self.paper_id)
        self.assertEqual(await collections.collector_counts([self.paper_id]), {self.paper_id: 2})

        # Moving between folders of the same user also keeps the count unchanged.
        await collections.update_paper_folders(
            self.user_a, self.paper_id, [folder_ids[1], folder_ids[2]],
        )
        self.assertEqual(await collections.collector_counts([self.paper_id]), {self.paper_id: 2})

        # Removing every folder drops the user.
        await collections.update_paper_folders(self.user_a, self.paper_id, [])
        self.assertEqual(await collections.collector_counts([self.paper_id]), {self.paper_id: 1})

        await collections.remove_paper(self.user_b, second_user_folder, self.paper_id)
        self.assertEqual(await collections.collector_counts([self.paper_id]), {})
        self.assertEqual(await collections.collector_counts([]), {})
        self.assertEqual(await collections.paper_folder_map(self.user_b, [self.paper_id]), {})

    async def test_like_and_follow_are_idempotent_per_user(self):
        likes = PaperLikeService()
        follows = TopicFollowService()

        self.assertEqual(await likes.like(self.user_a, self.like_paper_id), 1)
        self.assertEqual(await likes.like(self.user_a, self.like_paper_id), 1)
        self.assertEqual(await likes.like(self.user_b, self.like_paper_id), 2)
        self.assertEqual(await likes.like_counts([self.like_paper_id]), {self.like_paper_id: 2})
        self.assertEqual(await likes.liked_paper_ids(self.user_a, [self.like_paper_id]), {self.like_paper_id})
        self.assertEqual(await likes.unlike(self.user_a, self.like_paper_id), 1)
        self.assertEqual(await likes.unlike(self.user_a, self.like_paper_id), 1)

        self.assertEqual(await follows.follow(self.user_a, self.topic_id), 1)
        self.assertEqual(await follows.follow(self.user_a, self.topic_id), 1)
        self.assertEqual(await follows.follow(self.user_b, self.topic_id), 2)
        self.assertEqual(await follows.follower_counts([self.topic_id]), {self.topic_id: 2})
        self.assertEqual(await follows.followed_topic_ids(self.user_a, [self.topic_id]), {self.topic_id})
        self.assertEqual(await follows.unfollow(self.user_a, self.topic_id), 1)
        self.assertEqual(await follows.unfollow(self.user_a, self.topic_id), 1)
        # Unfollowing never validates the catalog, so stale ids can always be released.
        self.assertEqual(await follows.unfollow(self.user_b, 'removed-from-catalog'), 0)

        with self.assertRaises(BusinessError) as caught:
            await follows.follow(self.user_a, 'missing-topic')
        self.assertEqual(caught.exception.status, 404)

    async def test_api_roundtrip_exposes_live_counts_and_personal_state(self):
        from unittest.mock import patch

        import httpx

        from app.main import app

        collections = CollectionService()
        folder_id = (await collections.folders(self.user_a)).folders[0].id
        await collections.update_paper_folders(self.user_a, self.paper_id, [folder_id])
        await PaperLikeService().like(self.user_b, self.paper_id)
        await TopicFollowService().follow(self.user_a, self.topic_id)

        user_headers = {'x-shenzhi-bff-secret': 'test-secret', 'x-shenzhi-user-id': self.user_a}
        anonymous_headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }
        transport = httpx.ASGITransport(app=app)
        with patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'}):
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
                anonymous = await client.post(
                    '/api/v1/papers/interactions',
                    headers=anonymous_headers,
                    json={'paper_ids': [self.paper_id]},
                )
                authenticated = await client.post(
                    '/api/v1/papers/interactions',
                    headers=user_headers,
                    json={'paper_ids': [self.paper_id]},
                )
                topics = await client.post(
                    '/api/v1/topics/interactions',
                    headers=user_headers,
                    json={'topic_ids': [self.topic_id]},
                )
                liked = await client.put(f'/api/v1/papers/{self.paper_id}/like', headers=user_headers)
                forbidden = await client.put(f'/api/v1/papers/{self.paper_id}/like', headers=anonymous_headers)

        anonymous_item = anonymous.json()['data']['items'][0]
        self.assertEqual(anonymous_item['collector_count'], 1)
        self.assertEqual(anonymous_item['like_count'], 1)
        self.assertIsNone(anonymous_item['folder_ids'])
        self.assertIsNone(anonymous_item['liked'])

        authenticated_item = authenticated.json()['data']['items'][0]
        self.assertEqual(authenticated_item['folder_ids'], [folder_id])
        self.assertFalse(authenticated_item['liked'])
        self.assertEqual(authenticated_item['like_count'], 1)

        self.assertTrue(topics.json()['data']['items'][0]['is_following'])
        self.assertEqual(topics.json()['data']['items'][0]['follower_count'], 1)
        self.assertEqual(liked.json()['data']['like_count'], 2)
        self.assertEqual(forbidden.status_code, 401)

    async def test_account_deletion_removes_likes_and_follows(self):
        likes = PaperLikeService()
        follows = TopicFollowService()
        await likes.like(self.user_a, self.like_paper_id)
        await likes.like(self.user_b, self.like_paper_id)
        await follows.follow(self.user_a, self.topic_id)
        await follows.follow(self.user_b, self.topic_id)

        await AccountDeletionService().delete_all_for_user(self.user_a)

        self.assertEqual(await likes.like_counts([self.like_paper_id]), {self.like_paper_id: 1})
        self.assertEqual(await follows.follower_counts([self.topic_id]), {self.topic_id: 1})
        async with session_scope() as db:
            self.assertEqual(
                list(await db.scalars(select(PaperLikeRow).where(PaperLikeRow.user_id == self.user_a))), [],
            )
            self.assertEqual(
                list(await db.scalars(select(TopicFollowRow).where(TopicFollowRow.user_id == self.user_a))), [],
            )

        # Repeating the deletion stays safe and leaves the other account untouched.
        await AccountDeletionService().delete_all_for_user(self.user_a)
        self.assertEqual(await likes.liked_paper_ids(self.user_b, [self.like_paper_id]), {self.like_paper_id})

    async def test_concurrent_likes_and_follows_preserve_unique_user_relations(self):
        likes, follows = PaperLikeService(), TopicFollowService()
        await asyncio.gather(*(
            operation(user, identifier)
            for _ in range(8)
            for user in (self.user_a, self.user_b)
            for operation, identifier in ((likes.like, self.paper_id), (follows.follow, self.topic_id))
        ))
        self.assertEqual(await likes.like_counts([self.paper_id]), {self.paper_id: 2})
        self.assertEqual(await follows.follower_counts([self.topic_id]), {self.topic_id: 2})
        await asyncio.gather(*(
            operation(self.user_a, identifier)
            for _ in range(8)
            for operation, identifier in ((likes.unlike, self.paper_id), (follows.unfollow, self.topic_id))
        ))
        self.assertEqual(await likes.liked_paper_ids(self.user_a, [self.paper_id]), set())
        self.assertEqual(await likes.liked_paper_ids(self.user_b, [self.paper_id]), {self.paper_id})
        self.assertEqual(await follows.followed_topic_ids(self.user_a, [self.topic_id]), set())
        self.assertEqual(await follows.followed_topic_ids(self.user_b, [self.topic_id]), {self.topic_id})

    async def test_concurrent_disjoint_collection_replacements_do_not_union(self):
        collections = CollectionService()
        folders = [item.id for item in (await collections.folders(self.user_a)).folders]
        for _ in range(4):
            await collections.update_paper_folders(self.user_a, self.paper_id, [])
            await asyncio.gather(*(
                collections.update_paper_folders(self.user_a, self.paper_id, [folder]) for folder in folders
            ))
            memberships = await collections.paper_folders(self.user_a, self.paper_id)
            self.assertEqual(len(memberships), 1)
            self.assertIn(memberships[0], folders)
            self.assertEqual(await collections.collector_counts([self.paper_id]), {self.paper_id: 1})
        with self.assertRaises(BusinessError):
            await collections.update_paper_folders(self.user_b, self.paper_id, [folders[0]])
        self.assertEqual(await collections.paper_folders(self.user_b, self.paper_id), [])

    async def test_move_preserves_counts_and_rolls_back_if_target_is_full(self):
        collections = CollectionService()
        folders = [item.id for item in (await collections.folders(self.user_a)).folders]
        await collections.update_paper_folders(self.user_a, self.paper_id, [folders[0]])
        await collections.move_paper(self.user_a, folders[0], self.paper_id, folders[1])
        self.assertEqual(await collections.collector_counts([self.paper_id]), {self.paper_id: 1})
        async with session_scope() as db:
            db.add_all([CollectionItemRow(folder_id=folders[2], paper_id=f'capacity:{i}') for i in range(100)])
        with self.assertRaises(BusinessError) as caught:
            await collections.move_paper(self.user_a, folders[1], self.paper_id, folders[2])
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(await collections.paper_folders(self.user_a, self.paper_id), [folders[1]])
        await collections.delete_folder(self.user_a, folders[1])
        self.assertEqual(await collections.collector_counts([self.paper_id]), {})


if __name__ == '__main__':
    unittest.main()
