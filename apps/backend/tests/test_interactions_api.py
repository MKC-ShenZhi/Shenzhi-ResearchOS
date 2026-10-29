"""Interaction routes keep public counters anonymous and personal state private."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.interactions import LikedPaperListResponse, TopicFollowListResponse
from app.services.library.interactions import PaperInteraction, TopicInteraction


class InteractionApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.client = TestClient(app)
        self.user_headers = {'x-shenzhi-bff-secret': 'test-secret', 'x-shenzhi-user-id': 'user-a'}
        self.anonymous_headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }

    def tearDown(self):
        self.env.stop()

    def test_paper_interactions_are_public_but_personal_fields_need_identity(self):
        public = [PaperInteraction(paper_id='paper-1', collector_count=3, like_count=2)]
        personal = [PaperInteraction(
            paper_id='paper-1', collector_count=3, like_count=2, folder_ids=[7], liked=True,
        )]
        with patch(
            'app.api.interactions.interactions.paper_states', new=AsyncMock(return_value=public),
        ) as states:
            response = self.client.post(
                '/api/v1/papers/interactions',
                headers=self.anonymous_headers,
                json={'paper_ids': ['paper-1']},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['data']['authenticated'])
        self.assertIsNone(response.json()['data']['user_id'])
        self.assertEqual(response.json()['data']['items'], [{
            'paper_id': 'paper-1', 'collector_count': 3, 'like_count': 2,
            'folder_ids': None, 'liked': None,
        }])
        states.assert_awaited_once_with(None, ['paper-1'])

        with patch(
            'app.api.interactions.interactions.paper_states', new=AsyncMock(return_value=personal),
        ) as states:
            response = self.client.post(
                '/api/v1/papers/interactions',
                headers=self.user_headers,
                json={'paper_ids': ['paper-1', 'paper-1']},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['data']['authenticated'])
        self.assertEqual(response.json()['data']['user_id'], 'user-a')
        self.assertEqual(response.json()['data']['items'][0]['folder_ids'], [7])
        self.assertTrue(response.json()['data']['items'][0]['liked'])
        # Duplicate ids collapse before the service runs.
        states.assert_awaited_once_with('user-a', ['paper-1'])

    def test_topic_interactions_follow_the_same_visibility_rule(self):
        with patch(
            'app.api.interactions.interactions.topic_states',
            new=AsyncMock(return_value=[TopicInteraction(
                topic_id='deep-learning', follower_count=4, is_following=True,
            )]),
        ) as states:
            response = self.client.post(
                '/api/v1/topics/interactions',
                headers=self.user_headers,
                json={'topic_ids': ['deep-learning']},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['items'], [{
            'topic_id': 'deep-learning', 'follower_count': 4, 'is_following': True,
        }])
        states.assert_awaited_once_with('user-a', ['deep-learning'])

    def test_anonymous_writes_reject_before_touching_persistence(self):
        with (
            patch('app.api.interactions.likes.like', new=AsyncMock()) as like,
            patch('app.api.interactions.likes.unlike', new=AsyncMock()) as unlike,
            patch('app.api.interactions.follows.follow', new=AsyncMock()) as follow,
            patch('app.api.interactions.follows.unfollow', new=AsyncMock()) as unfollow,
            patch('app.api.interactions.likes.liked_papers', new=AsyncMock()) as liked_papers,
            patch('app.api.interactions.follows.list_follows', new=AsyncMock()) as list_follows,
        ):
            for method, path in (
                ('put', '/api/v1/papers/paper-1/like'),
                ('delete', '/api/v1/papers/paper-1/like'),
                ('put', '/api/v1/topic-follows/deep-learning'),
                ('delete', '/api/v1/topic-follows/deep-learning'),
                ('get', '/api/v1/likes'),
                ('get', '/api/v1/topic-follows'),
            ):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path, headers=self.anonymous_headers)
                    self.assertEqual(response.status_code, 401, response.text)
            for service in (like, unlike, follow, unfollow, liked_papers, list_follows):
                service.assert_not_awaited()

    def test_writes_use_the_trusted_identity_and_return_server_counts(self):
        with (
            patch('app.api.interactions.likes.like', new=AsyncMock(return_value=7)) as like,
            patch('app.api.interactions.follows.follow', new=AsyncMock(return_value=4)) as follow,
        ):
            liked = self.client.put(
                '/api/v1/papers/paper-1/like',
                headers=self.user_headers,
                json={'user_id': 'attacker'},
            )
            followed = self.client.put(
                '/api/v1/topic-follows/deep-learning?user_id=attacker',
                headers=self.user_headers,
            )
        self.assertEqual(liked.status_code, 200, liked.text)
        self.assertEqual(liked.json()['data'], {'paper_id': 'paper-1', 'liked': True, 'like_count': 7})
        self.assertEqual(followed.status_code, 200, followed.text)
        self.assertEqual(followed.json()['data'], {
            'topic_id': 'deep-learning', 'is_following': True, 'follower_count': 4,
        })
        like.assert_awaited_once_with('user-a', 'paper-1')
        follow.assert_awaited_once_with('user-a', 'deep-learning')

    def test_unlike_and_unfollow_are_idempotent_server_operations(self):
        with (
            patch('app.api.interactions.likes.unlike', new=AsyncMock(return_value=0)) as unlike,
            patch('app.api.interactions.follows.unfollow', new=AsyncMock(return_value=0)) as unfollow,
        ):
            liked = self.client.delete('/api/v1/papers/paper-1/like', headers=self.user_headers)
            followed = self.client.delete('/api/v1/topic-follows/deep-learning', headers=self.user_headers)
        self.assertEqual(liked.json()['data'], {'paper_id': 'paper-1', 'liked': False, 'like_count': 0})
        self.assertEqual(followed.json()['data'], {
            'topic_id': 'deep-learning', 'is_following': False, 'follower_count': 0,
        })
        unlike.assert_awaited_once_with('user-a', 'paper-1')
        unfollow.assert_awaited_once_with('user-a', 'deep-learning')

    def test_my_lists_are_scoped_to_the_authenticated_user(self):
        with (
            patch(
                'app.api.interactions.likes.liked_papers',
                new=AsyncMock(return_value=LikedPaperListResponse(items=[], total=0, page=1, page_size=20)),
            ) as liked_papers,
            patch(
                'app.api.interactions.follows.list_follows',
                new=AsyncMock(return_value=TopicFollowListResponse(items=[], total=0)),
            ) as list_follows,
        ):
            self.assertEqual(self.client.get('/api/v1/likes?page=2&page_size=10', headers=self.user_headers).status_code, 200)
            self.assertEqual(self.client.get('/api/v1/topic-follows', headers=self.user_headers).status_code, 200)
        liked_papers.assert_awaited_once_with('user-a', 2, 10)
        list_follows.assert_awaited_once_with('user-a')

    def test_stale_account_precondition_rejects_without_changing_request_owner(self):
        with patch('app.api.interactions.likes.like', new=AsyncMock(return_value=1)) as like:
            headers = {**self.user_headers, 'x-shenzhi-expected-user-id': 'user-b'}
            response = self.client.put('/api/v1/papers/paper-1/like', headers=headers)
            self.assertEqual(response.status_code, 409)
            like.assert_not_awaited()
            headers['x-shenzhi-expected-user-id'] = 'user-a'
            response = self.client.put('/api/v1/papers/paper-1/like', headers=headers)
            self.assertEqual(response.status_code, 200)
            like.assert_awaited_once_with('user-a', 'paper-1')

    def test_batch_and_identifier_limits_are_enforced(self):
        for payload in ({'paper_ids': []}, {'paper_ids': ['']}, {'paper_ids': [f'paper-{index}' for index in range(101)]}):
            with self.subTest(count=len(payload['paper_ids'])):
                response = self.client.post(
                    '/api/v1/papers/interactions', headers=self.user_headers, json=payload,
                )
                self.assertEqual(response.status_code, 422, response.text)

        for path in (
            f'/api/v1/papers/{"a" * 301}/like',
            '/api/v1/papers/%20paper-1%20/like',
            f'/api/v1/topic-follows/{"a" * 301}',
        ):
            with self.subTest(path=path):
                response = self.client.put(path, headers=self.user_headers)
                self.assertEqual(response.status_code, 422, response.text)


if __name__ == '__main__':
    unittest.main()
