"""Home discovery serves the complete packaged snapshot with stable cursors."""

import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.discovery import DiscoveryPaper
from app.services.discovery import (
    DiscoveryCandidate,
    DiscoverySnapshot,
    DiscoverySnapshotError,
    HomeDiscoveryService,
    _shanghai_today,
    load_discovery_snapshot,
)


def paper(index: int) -> DiscoveryPaper:
    return DiscoveryPaper(
        id=f'paper:2601.{index:05d}v1',
        title=f'Paper {index}',
        abstract=f'Abstract {index}',
        authors=[f'Author {index}'],
        year=2026,
        venue='arXiv',
        pdf_url=f'https://arxiv.org/pdf/2601.{index:05d}v1',
        thumbnail_url=f'/paper-thumbnails/2601.{index:05d}v1.webp',
    )


def candidate(index: int, priority: int = 1) -> DiscoveryCandidate:
    return DiscoveryCandidate(paper=paper(index), priority=priority)


class HomeDiscoveryServiceTests(unittest.TestCase):
    def test_packaged_snapshot_contains_300_unique_2026_papers(self):
        snapshot = load_discovery_snapshot()
        self.assertEqual(len(snapshot.items), 300)
        self.assertEqual(len({item.paper.id for item in snapshot.items}), 300)
        self.assertEqual({item.paper.year for item in snapshot.items}, {2026})
        self.assertEqual({item.priority for item in snapshot.items}, {1})
        self.assertTrue(all(
            item.paper.thumbnail_url and item.paper.thumbnail_url.endswith('.webp')
            for item in snapshot.items
        ))

    def test_cursor_walk_has_no_duplicates_or_omissions(self):
        service = HomeDiscoveryService(today_provider=lambda: date(2026, 10, 16))
        expected = {item.paper.id for item in load_discovery_snapshot().items}
        actual: list[str] = []
        cursor = None
        snapshot_id = None
        page_count = 0

        while True:
            page = service.page(limit=12, cursor=cursor)
            page_count += 1
            snapshot_id = snapshot_id or page.snapshot_id
            self.assertEqual(page.snapshot_id, snapshot_id)
            actual.extend(item.id for item in page.items)
            if not page.has_more:
                self.assertIsNone(page.next_cursor)
                break
            self.assertIsNotNone(page.next_cursor)
            cursor = page.next_cursor

        self.assertEqual(page_count, 25)
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(set(actual)), 300)

    def test_same_shanghai_day_is_stable_and_next_day_changes_order(self):
        snapshot = DiscoverySnapshot(
            snapshot_id='seed-test',
            items=tuple(candidate(index) for index in range(40)),
        )
        day_one = HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 16),
        ).page(limit=40)
        day_one_again = HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 16),
        ).page(limit=40)
        day_two = HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 17),
        ).page(limit=40)

        day_one_ids = [item.id for item in day_one.items]
        self.assertEqual(day_one_ids, [item.id for item in day_one_again.items])
        self.assertNotEqual(day_one_ids, [item.id for item in day_two.items])
        self.assertEqual(set(day_one_ids), {item.id for item in day_two.items})
        self.assertEqual(day_one.snapshot_id, 'seed-test:2026-10-16')
        self.assertEqual(day_two.snapshot_id, 'seed-test:2026-10-17')

    def test_daily_shuffle_never_crosses_priority_boundaries(self):
        snapshot = DiscoverySnapshot(
            snapshot_id='mixed-priority',
            items=tuple(
                candidate(index + priority * 100, priority)
                for priority in (4, 2, 1, 3)
                for index in range(6)
            ),
        )
        paper_priorities = {item.paper.id: item.priority for item in snapshot.items}
        page = HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 16),
        ).page(limit=100)
        priorities = [paper_priorities[item.id] for item in page.items]
        self.assertEqual(priorities, sorted(priorities))

    def test_cursor_keeps_original_daily_snapshot_after_midnight(self):
        snapshot = DiscoverySnapshot(
            snapshot_id='seed-midnight',
            items=tuple(candidate(index) for index in range(30)),
        )
        current_day = [date(2026, 10, 16)]
        service = HomeDiscoveryService(lambda: snapshot, today_provider=lambda: current_day[0])
        first = service.page(limit=12)
        current_day[0] = date(2026, 10, 17)
        second_from_cursor = service.page(limit=12, cursor=first.next_cursor)
        fresh_next_day = service.page(limit=12)
        full_day_one = HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 16),
        ).page(limit=30)

        self.assertEqual(second_from_cursor.snapshot_id, first.snapshot_id)
        self.assertEqual(
            [item.id for item in second_from_cursor.items],
            [item.id for item in full_day_one.items[12:24]],
        )
        self.assertTrue(
            {item.id for item in first.items}.isdisjoint(
                {item.id for item in second_from_cursor.items},
            ),
        )
        self.assertEqual(fresh_next_day.snapshot_id, 'seed-midnight:2026-10-17')

    def test_shanghai_day_rolls_over_at_1600_utc(self):
        with patch(
            'app.services.discovery.utc_now',
            return_value=datetime(2026, 10, 16, 15, 59, 59, tzinfo=timezone.utc),
        ):
            self.assertEqual(_shanghai_today(), date(2026, 10, 16))
        with patch(
            'app.services.discovery.utc_now',
            return_value=datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc),
        ):
            self.assertEqual(_shanghai_today(), date(2026, 10, 17))

    def test_empty_snapshot_returns_a_valid_empty_page(self):
        snapshot = DiscoverySnapshot(snapshot_id='empty-v1', items=())
        page = HomeDiscoveryService(lambda: snapshot).page(limit=12)
        self.assertEqual(page.items, [])
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_cursor)
        self.assertEqual(page.total, 0)

    def test_invalid_and_stale_cursors_are_rejected(self):
        first = HomeDiscoveryService().page(limit=12)
        with self.assertRaisesRegex(ValueError, '游标无效'):
            HomeDiscoveryService().page(limit=12, cursor='not-a-cursor')

        other = DiscoverySnapshot(
            snapshot_id='other-v1',
            items=tuple(candidate(index) for index in range(20)),
        )
        with self.assertRaisesRegex(ValueError, '已更新'):
            HomeDiscoveryService(lambda: other).page(limit=12, cursor=first.next_cursor)

    def test_snapshot_loader_errors_are_explicit(self):
        with self.assertRaises(DiscoverySnapshotError):
            HomeDiscoveryService(lambda: (_ for _ in ()).throw(DiscoverySnapshotError('bad'))).page(limit=12)


class HomeDiscoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }

    def tearDown(self):
        self.env.stop()

    def test_first_page_defaults_to_12_items(self):
        response = self.client.get('/api/v1/discovery/papers', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()['data']
        self.assertEqual(len(body['items']), 12)
        self.assertEqual(body['total'], 300)
        self.assertTrue(body['has_more'])
        self.assertIsNotNone(body['next_cursor'])
        self.assertTrue(body['snapshot_id'].startswith('seed-'))
        self.assertNotIn('doi', body['items'][0])

    def test_cursor_fetches_the_next_distinct_page(self):
        first = self.client.get('/api/v1/discovery/papers', headers=self.headers).json()['data']
        second = self.client.get(
            '/api/v1/discovery/papers',
            params={'limit': 12, 'cursor': first['next_cursor']},
            headers=self.headers,
        ).json()['data']
        self.assertEqual(first['snapshot_id'], second['snapshot_id'])
        self.assertTrue({item['id'] for item in first['items']}.isdisjoint(
            {item['id'] for item in second['items']},
        ))

    def test_invalid_parameters_and_cursor_return_client_errors(self):
        invalid_limit = self.client.get('/api/v1/discovery/papers?limit=0', headers=self.headers)
        invalid_cursor = self.client.get('/api/v1/discovery/papers?cursor=broken', headers=self.headers)
        self.assertEqual(invalid_limit.status_code, 422)
        self.assertEqual(invalid_cursor.status_code, 400)
        self.assertEqual(invalid_cursor.json()['code'], 20001)

    def test_snapshot_failure_returns_recoverable_service_error(self):
        with patch(
            'app.api.discovery.service.page',
            side_effect=DiscoverySnapshotError('missing'),
        ):
            response = self.client.get('/api/v1/discovery/papers', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 20004)


if __name__ == '__main__':
    unittest.main()
