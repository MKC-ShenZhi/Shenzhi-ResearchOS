"""Daily discovery pools are stable, database-backed, and refreshed atomically."""

import os
import unittest
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.identity import RequestIdentity
from app.main import app
from app.schemas.discovery import DailyRecommendationResponse
from app.schemas.knowledge import KnowledgeSearchResponse, PaperSearchResult, Provenance
from app.services.daily_recommendations import (
    DAILY_RECOMMENDATION_QUERIES,
    DailyRecommendationService,
    select_recommendations,
)


def paper(index: int, *, year: int = 2026) -> PaperSearchResult:
    paper_id = f'paper:{index}'
    return PaperSearchResult(
        id=paper_id,
        title=f'Paper {index}',
        year=year,
        provenance=Provenance(external_id=paper_id),
    )


class _FakeSession:
    def __init__(self, row=None):
        self.row = row
        self.executed = []

    async def scalar(self, _statement):
        return self.row

    async def execute(self, statement):
        self.executed.append(statement)


def _scope(session: _FakeSession):
    @asynccontextmanager
    async def context():
        yield session

    return context()


class DailyRecommendationServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_same_identity_day_and_tab_have_stable_order(self):
        items = [paper(index) for index in range(12)]
        identity = RequestIdentity(kind='user', subject_id='user-a')

        first = select_recommendations(
            items, identity=identity, day=date(2026, 9, 30), tab='recommend', limit=8,
        )
        second = select_recommendations(
            list(reversed(items)), identity=identity, day=date(2026, 9, 30), tab='recommend', limit=8,
        )

        self.assertEqual([item.id for item in first], [item.id for item in second])
        self.assertNotEqual(
            [item.id for item in first],
            [item.id for item in select_recommendations(
                items,
                identity=identity,
                day=date(2026, 10, 1),
                tab='recommend',
                limit=8,
            )],
        )
        self.assertNotEqual(
            [item.id for item in first],
            [item.id for item in select_recommendations(
                items,
                identity=RequestIdentity(kind='user', subject_id='user-b'),
                day=date(2026, 9, 30),
                tab='recommend',
                limit=8,
            )],
        )

    def test_frontier_uses_only_recent_candidates(self):
        selected = select_recommendations(
            [paper(1, year=2024), paper(2, year=2025), paper(3, year=2026)],
            identity=RequestIdentity(kind='anonymous', subject_id='anon-a'),
            day=date(2026, 9, 30),
            tab='frontier',
            limit=8,
        )
        self.assertEqual({item.id for item in selected}, {'paper:2', 'paper:3'})

    async def test_read_uses_latest_saved_pool_without_calling_knowledge(self):
        row = SimpleNamespace(payload=[paper(index).model_dump(mode='json') for index in range(10)])
        session = _FakeSession(row)
        knowledge = AsyncMock()
        service = DailyRecommendationService(knowledge=knowledge)

        with patch('app.services.daily_recommendations.session_scope', lambda: _scope(session)):
            response = await service.recommendations(
                RequestIdentity(kind='user', subject_id='user-a'),
                tab='recommend',
                limit=8,
                day=date(2026, 9, 30),
            )

        self.assertEqual(response.date, date(2026, 9, 30))
        self.assertEqual(len(response.items), 8)
        knowledge.search.assert_not_awaited()

    async def test_empty_database_returns_empty_feed(self):
        session = _FakeSession()
        service = DailyRecommendationService(knowledge=AsyncMock())
        with patch('app.services.daily_recommendations.session_scope', lambda: _scope(session)):
            response = await service.recommendations(
                RequestIdentity(kind='user', subject_id='user-a'),
                tab='recommend',
                limit=8,
                day=date(2026, 9, 30),
            )
        self.assertEqual(response.items, [])

    async def test_refresh_deduplicates_then_writes_once(self):
        knowledge = AsyncMock()
        knowledge.search.return_value = KnowledgeSearchResponse(results=[paper(1), paper(2)])
        session = _FakeSession()
        service = DailyRecommendationService(knowledge=knowledge)

        with (
            patch('app.services.daily_recommendations.session_scope', lambda: _scope(session)),
            patch(
                'app.services.daily_recommendations.utc_now',
                return_value=datetime(2026, 9, 30, tzinfo=timezone.utc),
            ),
        ):
            count = await service.refresh()

        self.assertEqual(count, 2)
        self.assertEqual(knowledge.search.await_count, len(DAILY_RECOMMENDATION_QUERIES))
        self.assertEqual(len(session.executed), 1)

    async def test_refresh_failure_never_opens_write_transaction(self):
        knowledge = AsyncMock()
        knowledge.search.side_effect = RuntimeError('knowledge unavailable')
        service = DailyRecommendationService(knowledge=knowledge)

        with patch('app.services.daily_recommendations.session_scope') as session_scope:
            with self.assertRaisesRegex(RuntimeError, 'knowledge unavailable'):
                await service.refresh(date(2026, 9, 30))

        session_scope.assert_not_called()


class DailyRecommendationApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()

    def test_route_uses_existing_authenticated_identity(self):
        response_model = DailyRecommendationResponse(date=date(2026, 9, 30), items=[paper(1)])
        with patch(
            'app.api.discovery.service.recommendations',
            new=AsyncMock(return_value=response_model),
        ) as recommendations:
            response = self.client.get(
                '/api/v1/discovery/recommendations?tab=recommend&limit=8',
                headers={'x-shenzhi-bff-secret': 'test-secret', 'x-shenzhi-user-id': 'user-a'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['date'], '2026-09-30')
        self.assertEqual(response.json()['data']['items'][0]['id'], 'paper:1')
        identity = recommendations.await_args.args[0]
        self.assertEqual(identity, RequestIdentity(kind='user', subject_id='user-a'))

    def test_route_accepts_existing_anonymous_identity(self):
        response_model = DailyRecommendationResponse(date=date(2026, 9, 30), items=[])
        anonymous_id = '00000000-0000-4000-8000-000000000001'
        with patch(
            'app.api.discovery.service.recommendations',
            new=AsyncMock(return_value=response_model),
        ) as recommendations:
            response = self.client.get(
                '/api/v1/discovery/recommendations',
                headers={
                    'x-shenzhi-bff-secret': 'test-secret',
                    'x-shenzhi-anonymous-id': anonymous_id,
                },
            )

        self.assertEqual(response.status_code, 200)
        identity = recommendations.await_args.args[0]
        self.assertEqual(identity, RequestIdentity(kind='anonymous', subject_id=anonymous_id))


if __name__ == '__main__':
    unittest.main()
