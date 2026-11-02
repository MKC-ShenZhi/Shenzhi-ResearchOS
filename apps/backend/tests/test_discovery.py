"""Home discovery composes daily + trending, falls back to the packaged snapshot, with stable cursors."""

import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.discovery import DiscoveryPaper
from app.services.discovery import (
    DiscoveryCandidate,
    DiscoveryListChangedError,
    DiscoverySnapshot,
    DiscoverySnapshotError,
    HomeDiscoveryService as _HomeDiscoveryService,
    _shanghai_today,
    load_discovery_snapshot,
    parse_edition,
)
from app.services.home_feed import config


async def no_edition(_ordering_date):
    return ()


async def no_trending(_ordering_date):
    return []


def HomeDiscoveryService(*args, **kwargs):
    """Fallback-only behaviour unless a test supplies live sources."""
    kwargs.setdefault('edition_loader', no_edition)
    kwargs.setdefault('trending_loader', no_trending)
    return _HomeDiscoveryService(*args, **kwargs)


def by_date(lists):
    async def load(ordering_date):
        return lists.get(ordering_date, ())
    return load


def paper(index: int, venue: str = 'arXiv') -> DiscoveryPaper:
    return DiscoveryPaper(
        id=f'paper:2601.{index:05d}v1',
        title=f'Paper {index}',
        abstract=f'Abstract {index}',
        authors=[f'Author {index}'],
        year=2026,
        venue=venue,
        pdf_url=f'https://arxiv.org/pdf/2601.{index:05d}v1',
        thumbnail_url=f'/paper-thumbnails/2601.{index:05d}v1.webp',
    )


def pool_papers(indexes, venues=('AAAI', 'ACL', 'CVPR', 'ICLR', 'ICML', 'NeurIPS')):
    return tuple(paper(index, venues[index % len(venues)]).model_copy(
        update={'thumbnail_url': None, 'image_id': f'/images/p{index}.png'},
    ) for index in indexes)


def candidate(index: int, priority: int = 1) -> DiscoveryCandidate:
    return DiscoveryCandidate(paper=paper(index), priority=priority)


def snapshot_of(snapshot_id: str, count: int) -> DiscoverySnapshot:
    return DiscoverySnapshot(snapshot_id, tuple(candidate(index) for index in range(count)))


class PackagedSnapshotTests(unittest.TestCase):
    def test_packaged_snapshot_admits_only_displayable_2026_papers(self):
        snapshot = load_discovery_snapshot()
        ids = [item.paper.id for item in snapshot.items]
        self.assertGreaterEqual(len(ids), 290)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual({item.paper.year for item in snapshot.items}, {2026})
        self.assertTrue(all(
            item.paper.thumbnail_url and item.paper.thumbnail_url.endswith('.webp') for item in snapshot.items
        ))
        # Rule B drops the section-heading title and the truncated abstract shipped in the seed.
        self.assertNotIn('paper:2604.26488v1', ids)
        self.assertNotIn('paper:2604.08896v1', ids)


class FallbackListTests(unittest.IsolatedAsyncioTestCase):
    async def test_cursor_walk_has_no_duplicates_or_omissions(self):
        service = HomeDiscoveryService(today_provider=lambda: date(2026, 10, 16))
        expected = {item.paper.id for item in load_discovery_snapshot().items}
        actual: list[str] = []
        cursor, list_id = None, None
        while True:
            page = await service.page(limit=12, cursor=cursor)
            list_id = list_id or page.list_id
            self.assertEqual(page.list_id, list_id)
            actual.extend(item.id for item in page.items)
            self.assertEqual({item.source for item in page.items}, {'fallback'})
            if not page.has_more:
                self.assertIsNone(page.next_cursor)
                break
            cursor = page.next_cursor
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(set(actual), expected)

    async def test_same_shanghai_day_is_stable_and_next_day_changes_order(self):
        snapshot = snapshot_of('seed-test', 40)

        async def ids(day):
            page = await HomeDiscoveryService(lambda: snapshot, today_provider=lambda: day).page(limit=40)
            return [item.id for item in page.items]

        day_one = await ids(date(2026, 10, 16))
        self.assertEqual(day_one, await ids(date(2026, 10, 16)))
        day_two = await ids(date(2026, 10, 17))
        self.assertNotEqual(day_one, day_two)
        self.assertEqual(set(day_one), set(day_two))

    async def test_daily_shuffle_never_crosses_priority_boundaries(self):
        snapshot = DiscoverySnapshot('mixed-priority', tuple(
            candidate(index + priority * 100, priority) for priority in (4, 2, 1, 3) for index in range(6)
        ))
        priorities = {item.paper.id: item.priority for item in snapshot.items}
        page = await HomeDiscoveryService(lambda: snapshot, today_provider=lambda: date(2026, 10, 16)).page(limit=100)
        order = [priorities[item.id] for item in page.items]
        self.assertEqual(order, sorted(order))

    async def test_cursor_keeps_its_list_after_midnight(self):
        snapshot = snapshot_of('seed-midnight', 30)
        current_day = [date(2026, 10, 16)]
        service = HomeDiscoveryService(lambda: snapshot, today_provider=lambda: current_day[0])
        first = await service.page(limit=12)
        current_day[0] = date(2026, 10, 17)
        second = await service.page(limit=12, cursor=first.next_cursor)
        full_day_one = await HomeDiscoveryService(lambda: snapshot, today_provider=lambda: date(2026, 10, 16)).page(limit=30)
        self.assertEqual(second.list_id, first.list_id)
        self.assertEqual([item.id for item in second.items], [item.id for item in full_day_one.items[12:24]])
        self.assertNotEqual((await service.page(limit=12)).list_id, first.list_id)

    def test_shanghai_day_rolls_over_at_1600_utc(self):
        with patch('app.services.discovery.utc_now', return_value=datetime(2026, 10, 16, 15, 59, 59, tzinfo=timezone.utc)):
            self.assertEqual(_shanghai_today(), date(2026, 10, 16))
        with patch('app.services.discovery.utc_now', return_value=datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc)):
            self.assertEqual(_shanghai_today(), date(2026, 10, 17))

    async def test_empty_snapshot_and_no_sources_return_a_valid_empty_page(self):
        page = await HomeDiscoveryService(lambda: DiscoverySnapshot('empty-v1', ())).page(limit=12)
        self.assertEqual((page.items, page.has_more, page.next_cursor, page.total), ([], False, None, 0))

    async def test_invalid_and_stale_cursors_are_rejected(self):
        first = await HomeDiscoveryService().page(limit=12)
        with self.assertRaisesRegex(ValueError, '游标无效'):
            await HomeDiscoveryService().page(limit=12, cursor='not-a-cursor')
        with self.assertRaisesRegex(ValueError, '已更新'):
            await HomeDiscoveryService(lambda: snapshot_of('other-v1', 20)).page(limit=12, cursor=first.next_cursor)

    async def test_snapshot_errors_surface_only_when_nothing_else_is_available(self):
        def broken():
            raise DiscoverySnapshotError('bad')
        with self.assertRaises(DiscoverySnapshotError):
            await HomeDiscoveryService(broken).page(limit=12)
        day = date(2026, 11, 2)
        few = HomeDiscoveryService(broken, today_provider=lambda: day, edition_loader=by_date({day: pool_papers(range(5))}))
        self.assertEqual((await few.page(limit=12)).total, 5)

    async def test_snapshot_cursors_issued_before_composed_lists_keep_working(self):
        from app.services.discovery import _encode_cursor
        day = date(2026, 11, 2)
        snapshot = snapshot_of('seed-legacy', 30)
        later = HomeDiscoveryService(lambda: snapshot, today_provider=lambda: day,
                                     edition_loader=by_date({day: pool_papers(range(50, 100))}))
        page = await later.page(limit=12, cursor=_encode_cursor('seed-legacy:2026-11-02', day, 12))
        self.assertEqual(page.list_id, 'seed-legacy:2026-11-02')
        self.assertEqual(len(page.items), 12)


class ComposedListTests(unittest.IsolatedAsyncioTestCase):
    DAY = date(2026, 11, 2)

    def service(self, daily=(), trending=(), snapshot=None, **kwargs):
        loaded = []

        def snapshot_loader():
            loaded.append(True)
            return snapshot or snapshot_of('seed-composed', 60)
        service = HomeDiscoveryService(
            snapshot_loader, today_provider=lambda: self.DAY,
            edition_loader=by_date({self.DAY: tuple(daily)}),
            trending_loader=by_date({self.DAY: list(trending)}), **kwargs,
        )
        return service, loaded

    async def test_daily_and_trending_share_each_screen_by_quota(self):
        daily, trending = pool_papers(range(100)), pool_papers(range(500, 530))
        service, loaded = self.service(daily, trending)
        page = await service.page(limit=12)
        sources = [item.source for item in page.items]
        self.assertEqual((sources.count('daily'), sources.count('trending')), (10, 2))
        self.assertTrue(page.list_id.startswith('home:2026-11-02:'))
        self.assertEqual(page.total, 130)
        # Enough live papers: the packaged snapshot is never read.
        self.assertEqual(loaded, [])

    async def test_a_paper_in_two_sources_appears_once(self):
        daily = pool_papers(range(60))
        service, _ = self.service(daily, daily[:10])
        papers = (await service.list_for(self.DAY)).papers
        self.assertEqual(len(papers), 60)
        self.assertEqual(len({paper.id for paper in papers}), 60)

    async def test_fallback_is_appended_once_when_live_sources_fall_short(self):
        service, loaded = self.service(pool_papers(range(config.FALLBACK_MIN_ITEMS - 1)))
        papers = (await service.list_for(self.DAY)).papers
        self.assertEqual(loaded, [True])
        self.assertEqual({paper.source for paper in papers[:config.FALLBACK_MIN_ITEMS - 1]}, {'daily'})
        self.assertEqual({paper.source for paper in papers[config.FALLBACK_MIN_ITEMS - 1:]}, {'fallback'})
        # The composed list is cached, so paging does not re-trigger anything.
        await service.list_for(self.DAY)
        self.assertEqual(loaded, [True])

    async def test_no_screen_shows_one_venue_more_than_four_times(self):
        daily = pool_papers(range(48), venues=('AAAI', 'AAAI', 'AAAI', 'ACL', 'CVPR', 'ICLR'))
        service, _ = self.service(daily)
        papers = (await service.list_for(self.DAY)).papers
        for start in range(0, 36, config.SCREEN_SIZE):
            screen = [paper.venue for paper in papers[start:start + config.SCREEN_SIZE]]
            self.assertLessEqual(max(screen.count(venue) for venue in set(screen)), config.VENUE_PER_SCREEN)

    async def test_cursor_stays_on_its_list_and_rejects_a_republished_edition(self):
        service, _ = self.service(pool_papers(range(40)))
        first = await service.page(limit=12)
        second = await service.page(limit=12, cursor=first.next_cursor)
        self.assertTrue({item.id for item in first.items}.isdisjoint({item.id for item in second.items}))
        republished, _ = self.service(pool_papers(range(100, 140)))
        with self.assertRaisesRegex(DiscoveryListChangedError, '已更新'):
            await republished.page(limit=12, cursor=first.next_cursor)

    def test_stored_payloads_are_validated(self):
        valid = [paper(1).model_dump(mode='json')]
        self.assertIsNotNone(parse_edition(valid))
        for invalid in (None, [], {'items': valid}, [{'id': 'x'}], valid + valid,
                        [{**valid[0], 'thumbnail_url': None, 'image_id': None}]):
            self.assertIsNone(parse_edition(invalid), invalid)


class HomeDiscoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.patches = [
            patch('app.api.discovery.service._edition_loader', no_edition),
            patch('app.api.discovery.service._trending_loader', no_trending),
            patch.dict('app.api.discovery.service._lists', clear=True),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.env.stop()

    def test_first_page_defaults_to_12_items(self):
        response = self.client.get('/api/v1/discovery/papers', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()['data']
        self.assertEqual(len(body['items']), 12)
        self.assertEqual(body['total'], len(load_discovery_snapshot().items))
        self.assertTrue(body['has_more'])
        self.assertIsNotNone(body['next_cursor'])
        self.assertTrue(body['list_id'].startswith('home:'))
        self.assertEqual(body['items'][0]['source'], 'fallback')
        self.assertNotIn('doi', body['items'][0])

    def test_cursor_fetches_the_next_distinct_page(self):
        first = self.client.get('/api/v1/discovery/papers', headers=self.headers).json()['data']
        second = self.client.get(
            '/api/v1/discovery/papers', params={'limit': 12, 'cursor': first['next_cursor']}, headers=self.headers,
        ).json()['data']
        self.assertEqual(first['list_id'], second['list_id'])
        self.assertTrue({item['id'] for item in first['items']}.isdisjoint({item['id'] for item in second['items']}))

    def test_invalid_parameters_and_cursor_return_client_errors(self):
        invalid_limit = self.client.get('/api/v1/discovery/papers?limit=0', headers=self.headers)
        invalid_cursor = self.client.get('/api/v1/discovery/papers?cursor=broken', headers=self.headers)
        self.assertEqual(invalid_limit.status_code, 422)
        self.assertEqual(invalid_cursor.status_code, 400)
        self.assertEqual(invalid_cursor.json()['code'], 20001)

    def test_replaced_list_returns_conflict_so_the_client_restarts(self):
        first = self.client.get('/api/v1/discovery/papers', headers=self.headers).json()['data']
        with patch('app.api.discovery.service.page', side_effect=DiscoveryListChangedError('论文发现列表已更新')):
            stale = self.client.get(
                '/api/v1/discovery/papers', params={'cursor': first['next_cursor']}, headers=self.headers,
            )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()['code'], 20001)

    def test_snapshot_failure_returns_recoverable_service_error(self):
        with patch('app.api.discovery.service.page', side_effect=DiscoverySnapshotError('missing')):
            response = self.client.get('/api/v1/discovery/papers', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 20004)


if __name__ == '__main__':
    unittest.main()
