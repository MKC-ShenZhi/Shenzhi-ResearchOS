"""The statistics service identity is separate from BFF and user sessions."""

import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.stats import (
    PaperStatsItem,
    PaperStatsPage,
    StatsMetaResponse,
    TopicStatsItem,
    TopicStatsPage,
)


class StatsApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'BACKEND_BFF_SECRET': 'bff-secret',
            'STATS_SERVICE_TOKEN': 'stats-secret',
        })
        self.env.start()
        self.client = TestClient(app)
        self.headers = {'x-shenzhi-stats-token': 'stats-secret'}
        self.day = date(2026, 10, 20)
        self.computed_at = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.env.stop()

    def test_service_token_is_required_and_separate_from_bff_credentials(self):
        with patch.dict(os.environ, {'STATS_SERVICE_TOKEN': ''}):
            self.assertEqual(self.client.get('/api/v1/stats/meta', headers=self.headers).status_code, 503)

        for headers in (
            {},
            {'x-shenzhi-stats-token': 'wrong'},
            {'x-shenzhi-bff-secret': 'bff-secret'},
            {'x-shenzhi-bff-secret': 'bff-secret', 'x-shenzhi-user-id': 'user-a'},
            {'x-shenzhi-bff-secret': 'bff-secret', 'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get('/api/v1/stats/meta', headers=headers).status_code, 401)

    def test_stats_credential_cannot_read_personal_data(self):
        response = self.client.get('/api/v1/likes', headers={
            'x-shenzhi-stats-token': 'stats-secret',
            'x-shenzhi-user-id': 'user-a',
        })
        self.assertEqual(response.status_code, 401, response.text)

    def test_meta_is_served_for_the_service_identity(self):
        meta = StatsMetaResponse(
            published=True, snapshot_date=self.day, snapshot_version='v1', computed_at=self.computed_at,
        )
        with patch('app.api.stats.service.meta', new=AsyncMock(return_value=meta)) as call:
            response = self.client.get('/api/v1/stats/meta', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data'], {
            'published': True,
            'snapshot_date': '2026-10-20',
            'snapshot_version': 'v1',
            'computed_at': '2026-10-20T01:00:00Z',
        })
        call.assert_awaited_once_with()

    def test_paper_page_forwards_filters_and_limits(self):
        page = PaperStatsPage(
            snapshot_date=self.day,
            snapshot_version='v1',
            computed_at=self.computed_at,
            items=[PaperStatsItem(paper_id='paper-1', collector_count=3, like_count=1)],
            total=1,
        )
        with patch('app.api.stats.service.papers_page', new=AsyncMock(return_value=page)) as call:
            response = self.client.get(
                '/api/v1/stats/papers?date=2026-10-20&limit=2&paper_id=paper-1',
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['items'][0]['collector_count'], 3)
        call.assert_awaited_once_with(
            snapshot_date=self.day, limit=2, cursor=None, paper_ids=['paper-1'],
        )

    def test_topic_page_forwards_cursor(self):
        page = TopicStatsPage(
            snapshot_date=self.day,
            snapshot_version='v1',
            computed_at=self.computed_at,
            items=[TopicStatsItem(topic_id='deep-learning', follower_count=2)],
            total=1,
        )
        with patch('app.api.stats.service.topics_page', new=AsyncMock(return_value=page)) as call:
            response = self.client.get(
                '/api/v1/stats/topics?date=2026-10-20&limit=5&cursor=abc',
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200, response.text)
        call.assert_awaited_once_with(
            snapshot_date=self.day, limit=5, cursor='abc', topic_ids=None,
        )

    def test_invalid_arguments_are_rejected_before_the_service_runs(self):
        with patch('app.api.stats.service.papers_page', new=AsyncMock()) as papers, \
                patch('app.api.stats.service.topics_page', new=AsyncMock()) as topics:
            self.assertEqual(self.client.get('/api/v1/stats/papers?date=20-10-2026', headers=self.headers).status_code, 400)
            self.assertEqual(self.client.get('/api/v1/stats/topics?date=not-a-date', headers=self.headers).status_code, 400)
            too_many = '&'.join(f'paper_id=paper-{index}' for index in range(101))
            self.assertEqual(self.client.get(f'/api/v1/stats/papers?{too_many}', headers=self.headers).status_code, 422)
            long_id = f'{"a" * 301}'
            self.assertEqual(self.client.get(f'/api/v1/stats/topics?topic_id={long_id}', headers=self.headers).status_code, 422)
        papers.assert_not_awaited()
        topics.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
