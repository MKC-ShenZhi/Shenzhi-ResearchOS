"""Home discovery serves the daily edition, or the packaged snapshot, with stable cursors."""

import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.discovery import DiscoveryPaper
from app.services.discovery import (
    DailyList,
    DiscoveryCandidate,
    DiscoverySnapshot,
    DiscoverySnapshotError,
    HomeDiscoveryService as _HomeDiscoveryService,
    _shanghai_today,
    edition_id,
    load_discovery_snapshot,
    parse_edition,
)


async def no_edition(_ordering_date):
    return None


def HomeDiscoveryService(*args, **kwargs):
    """Packaged-snapshot behaviour unless a test supplies stored editions."""
    kwargs.setdefault('edition_loader', no_edition)
    return _HomeDiscoveryService(*args, **kwargs)


def editions(*lists: DailyList):
    by_date = {daily.ordering_date: daily for daily in lists}

    async def load(ordering_date):
        return by_date.get(ordering_date)
    return load


def edition(ordering_date: date, indexes) -> DailyList:
    papers = tuple(paper(index).model_copy(update={'thumbnail_url': None, 'image_id': f'/images/p{index}.png'})
                   for index in indexes)
    return DailyList(edition_id(ordering_date, papers), ordering_date, papers)


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


class HomeDiscoveryServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_cursor_walk_has_no_duplicates_or_omissions(self):
        service = HomeDiscoveryService(today_provider=lambda: date(2026, 10, 16))
        expected = {item.paper.id for item in load_discovery_snapshot().items}
        actual: list[str] = []
        cursor = None
        snapshot_id = None
        page_count = 0

        while True:
            page = await service.page(limit=12, cursor=cursor)
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

    async def test_same_shanghai_day_is_stable_and_next_day_changes_order(self):
        snapshot = DiscoverySnapshot(
            snapshot_id='seed-test',
            items=tuple(candidate(index) for index in range(40)),
        )
        day_one = await HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 16),
        ).page(limit=40)
        day_one_again = await HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 16),
        ).page(limit=40)
        day_two = await HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 17),
        ).page(limit=40)

        day_one_ids = [item.id for item in day_one.items]
        self.assertEqual(day_one_ids, [item.id for item in day_one_again.items])
        self.assertNotEqual(day_one_ids, [item.id for item in day_two.items])
        self.assertEqual(set(day_one_ids), {item.id for item in day_two.items})
        self.assertEqual(day_one.snapshot_id, 'seed-test:2026-10-16')
        self.assertEqual(day_two.snapshot_id, 'seed-test:2026-10-17')
        # Personal feeds continue with exactly the same complete daily order.
        self.assertEqual([item.id for item in await HomeDiscoveryService(
            lambda: snapshot, today_provider=lambda: date(2026, 10, 16),
        ).daily_papers()], day_one_ids)

    async def test_daily_shuffle_never_crosses_priority_boundaries(self):
        snapshot = DiscoverySnapshot(
            snapshot_id='mixed-priority',
            items=tuple(
                candidate(index + priority * 100, priority)
                for priority in (4, 2, 1, 3)
                for index in range(6)
            ),
        )
        paper_priorities = {item.paper.id: item.priority for item in snapshot.items}
        page = await HomeDiscoveryService(
            lambda: snapshot,
            today_provider=lambda: date(2026, 10, 16),
        ).page(limit=100)
        priorities = [paper_priorities[item.id] for item in page.items]
        self.assertEqual(priorities, sorted(priorities))

    async def test_cursor_keeps_original_daily_snapshot_after_midnight(self):
        snapshot = DiscoverySnapshot(
            snapshot_id='seed-midnight',
            items=tuple(candidate(index) for index in range(30)),
        )
        current_day = [date(2026, 10, 16)]
        service = HomeDiscoveryService(lambda: snapshot, today_provider=lambda: current_day[0])
        first = await service.page(limit=12)
        current_day[0] = date(2026, 10, 17)
        second_from_cursor = await service.page(limit=12, cursor=first.next_cursor)
        fresh_next_day = await service.page(limit=12)
        full_day_one = await HomeDiscoveryService(
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

    async def test_empty_snapshot_returns_a_valid_empty_page(self):
        snapshot = DiscoverySnapshot(snapshot_id='empty-v1', items=())
        page = await HomeDiscoveryService(lambda: snapshot).page(limit=12)
        self.assertEqual(page.items, [])
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_cursor)
        self.assertEqual(page.total, 0)

    async def test_invalid_and_stale_cursors_are_rejected(self):
        first = await HomeDiscoveryService().page(limit=12)
        with self.assertRaisesRegex(ValueError, '游标无效'):
            await HomeDiscoveryService().page(limit=12, cursor='not-a-cursor')

        other = DiscoverySnapshot(
            snapshot_id='other-v1',
            items=tuple(candidate(index) for index in range(20)),
        )
        with self.assertRaisesRegex(ValueError, '已更新'):
            await HomeDiscoveryService(lambda: other).page(limit=12, cursor=first.next_cursor)

    async def test_snapshot_loader_errors_are_explicit(self):
        with self.assertRaises(DiscoverySnapshotError):
            await HomeDiscoveryService(lambda: (_ for _ in ()).throw(DiscoverySnapshotError('bad'))).page(limit=12)

    async def test_stored_edition_wins_then_yesterday_then_the_packaged_snapshot(self):
        today, yesterday = date(2026, 11, 2), date(2026, 11, 1)
        snapshot = DiscoverySnapshot('seed-fallback', tuple(candidate(index) for index in range(5)))

        def service(*stored):
            return HomeDiscoveryService(lambda: snapshot, today_provider=lambda: today, edition_loader=editions(*stored))

        page = await service(edition(today, range(10, 13)), edition(yesterday, range(20, 22))).page(limit=12)
        self.assertEqual([item.id for item in page.items], [paper(index).id for index in range(10, 13)])
        self.assertTrue(page.snapshot_id.startswith('daily:2026-11-02:'))
        self.assertEqual(page.items[0].image_id, '/images/p10.png')
        page = await service(edition(yesterday, range(20, 22))).page(limit=12)
        self.assertEqual([item.id for item in page.items], [paper(index).id for index in range(20, 22)])
        page = await service().page(limit=12)
        self.assertEqual(page.snapshot_id, 'seed-fallback:2026-11-02')
        self.assertEqual(len(await service().daily_papers()), 5)

    async def test_cursor_stays_on_its_edition_and_rejects_a_republished_one(self):
        day = date(2026, 11, 2)
        first_edition = edition(day, range(30))
        snapshot = DiscoverySnapshot('seed-cursor', tuple(candidate(index) for index in range(5)))
        service = HomeDiscoveryService(lambda: snapshot, today_provider=lambda: day,
                                       edition_loader=editions(first_edition))
        first = await service.page(limit=12)
        second = await service.page(limit=12, cursor=first.next_cursor)
        self.assertEqual([item.id for item in second.items], [paper.id for paper in first_edition.papers[12:24]])
        # After midnight the cursor still reads the edition it started on.
        service._today_provider = lambda: date(2026, 11, 3)
        third = await service.page(limit=12, cursor=second.next_cursor)
        self.assertEqual(len(third.items), 6)
        self.assertFalse(third.has_more)
        # A republished edition for the same day invalidates old cursors.
        service._edition_loader = editions(edition(day, range(40, 70)))
        with self.assertRaisesRegex(ValueError, '已更新'):
            await service.page(limit=12, cursor=first.next_cursor)

    async def test_snapshot_cursors_issued_before_editions_keep_working(self):
        day = date(2026, 11, 2)
        snapshot = DiscoverySnapshot('seed-legacy', tuple(candidate(index) for index in range(30)))
        first = await HomeDiscoveryService(lambda: snapshot, today_provider=lambda: day).page(limit=12)
        # The edition published later the same day does not break the curated cursor.
        later = HomeDiscoveryService(lambda: snapshot, today_provider=lambda: day,
                                     edition_loader=editions(edition(day, range(50, 80))))
        second = await later.page(limit=12, cursor=first.next_cursor)
        self.assertEqual(second.snapshot_id, 'seed-legacy:2026-11-02')

    def test_stored_payloads_are_validated(self):
        day = date(2026, 11, 2)
        valid = [paper(1).model_dump(mode='json')]
        self.assertIsNotNone(parse_edition(day, valid))
        for invalid in (None, [], {'items': valid}, [{'id': 'x'}], valid + valid,
                        [{**valid[0], 'thumbnail_url': None, 'image_id': None}]):
            self.assertIsNone(parse_edition(day, invalid), invalid)


class HomeDiscoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.edition = patch('app.api.discovery.service._edition_loader', no_edition)
        self.edition.start()
        self.client = TestClient(app)
        self.headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }

    def tearDown(self):
        self.edition.stop()
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
