"""Conference deadlines: timezone conversion, edition selection, filters and API."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.conferences import (
    ConferenceDeadlineService,
    ConferenceFilters,
    ConferenceSnapshotError,
    UnknownCategoryError,
    load_conference_catalog,
    parse_timezone,
    read_catalog,
    to_utc,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def edition(year: int, *timeline: dict, tz: str = 'AoE') -> dict:
    return {
        'year': year, 'link': f'https://example.org/{year}', 'timezone': tz,
        'date': None, 'place': None, 'timeline': list(timeline),
    }


def conference(conference_id: str, *editions: dict, category: str = 'AI', **rank) -> dict:
    return {
        'id': conference_id, 'title': conference_id.split('-', 1)[1].upper(),
        'description': f'{conference_id} description', 'category': category,
        'dblp': conference_id, 'rank': {'ccf': None, 'core': None, 'thcpl': None, **rank},
        'editions': list(editions),
    }


def snapshot(*conferences: dict) -> dict:
    return {
        'schema_version': 1, 'snapshot_id': 'ccfddl-test', 'data_as_of': '2026-10-29',
        'source': {'name': 'ccf-deadlines', 'url': 'https://github.com/ccfddl/ccf-deadlines'},
        'categories': [
            {'id': 'AI', 'name': '人工智能', 'name_en': 'Artificial Intelligence'},
            {'id': 'NW', 'name': '计算机网络', 'name_en': 'Network System'},
        ],
        'conferences': list(conferences),
    }


class CatalogTestCase(unittest.TestCase):
    def service(self, payload: dict, now: datetime) -> ConferenceDeadlineService:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'snapshot.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            catalog = read_catalog(path)
        return ConferenceDeadlineService(catalog_loader=lambda: catalog, now_provider=lambda: now)


class TimezoneTests(unittest.TestCase):
    def test_aoe_is_utc_minus_12(self):
        self.assertEqual(to_utc('2026-08-01 23:59:59', parse_timezone('AoE')), utc(2026, 8, 2, 11, 59, 59))

    def test_fixed_offsets(self):
        self.assertEqual(to_utc('2026-08-01 20:00:00', parse_timezone('UTC+8')), utc(2026, 8, 1, 12))
        self.assertEqual(to_utc('2026-08-01 20:00:00', parse_timezone('UTC-7')), utc(2026, 8, 2, 3))
        self.assertEqual(to_utc('2026-08-01 20:00:00', parse_timezone('UTC')), utc(2026, 8, 1, 20))

    def test_pacific_time_follows_daylight_saving(self):
        self.assertEqual(to_utc('2026-07-01 17:00:00', parse_timezone('PT')), utc(2026, 7, 2, 0))
        self.assertEqual(to_utc('2026-12-01 17:00:00', parse_timezone('PT')), utc(2026, 12, 2, 1))

    def test_unknown_timezone_is_a_snapshot_error(self):
        for label in ('CET', 'UTC+15', 'utc+8', ''):
            with self.assertRaises(ConferenceSnapshotError, msg=label):
                parse_timezone(label)


class EditionSelectionTests(CatalogTestCase):
    def test_soonest_upcoming_milestone_wins_and_abstract_counts(self):
        payload = snapshot(conference(
            'ai-aaai',
            edition(2026, {'abstract_deadline': '2025-07-25 23:59:59', 'deadline': '2025-08-01 23:59:59'}),
            edition(2027, {'abstract_deadline': '2026-11-10 23:59:59', 'deadline': '2026-11-17 23:59:59'}),
        ))
        item = self.service(payload, utc(2026, 10, 29)).deadlines().items[0]
        self.assertEqual(item.status, 'open')
        self.assertEqual(item.edition.year, 2027)
        self.assertEqual(item.next_milestone.kind, 'abstract')
        self.assertEqual(item.next_milestone.at, utc(2026, 11, 11, 11, 59, 59))
        self.assertEqual(item.next_milestone.local, '2026-11-10 23:59:59')
        self.assertEqual(item.edition_count, 2)

        after_abstract = self.service(payload, utc(2026, 11, 12)).deadlines().items[0]
        self.assertEqual(after_abstract.next_milestone.kind, 'full')

    def test_multiple_rounds_keep_their_comments(self):
        payload = snapshot(conference('ai-acl', edition(
            2027,
            {'deadline': '2026-10-15 23:59:59', 'comment': 'first round'},
            {'deadline': '2026-12-15 23:59:59', 'comment': 'second round'},
        )))
        item = self.service(payload, utc(2026, 10, 29)).deadlines().items[0]
        self.assertEqual(item.next_milestone.comment, 'second round')
        self.assertEqual([m.comment for m in item.edition.milestones], ['first round', 'second round'])

    def test_newest_edition_with_tbd_is_tbd_and_tbd_sorts_last_in_timeline(self):
        payload = snapshot(conference(
            'ai-acl',
            edition(2026, {'deadline': '2025-10-15 23:59:59'}),
            edition(2027, {'deadline': None, 'comment': 'ARR'}, {'deadline': '2026-02-01 23:59:59'}),
        ))
        item = self.service(payload, utc(2026, 10, 29)).deadlines().items[0]
        self.assertEqual(item.status, 'tbd')
        self.assertEqual(item.edition.year, 2027)
        self.assertIsNone(item.next_milestone)
        self.assertEqual([m.at is None for m in item.edition.milestones], [False, True])

    def test_closed_uses_newest_edition_and_last_deadline(self):
        payload = snapshot(conference(
            'ai-ijcai',
            edition(2025, {'deadline': '2025-01-20 23:59:59'}),
            edition(2026, {'abstract_deadline': '2026-01-10 23:59:59', 'deadline': '2026-01-17 23:59:59'}),
        ))
        item = self.service(payload, utc(2026, 10, 29)).deadlines().items[0]
        self.assertEqual((item.status, item.edition.year), ('closed', 2026))
        self.assertEqual(item.last_deadline_at, utc(2026, 1, 18, 11, 59, 59))

    def test_deadline_is_exclusive_at_the_exact_instant(self):
        payload = snapshot(conference('ai-x', edition(2027, {'deadline': '2026-11-01 00:00:00'}, tz='UTC')))
        self.assertEqual(self.service(payload, utc(2026, 11, 1)).deadlines().items[0].status, 'closed')


class OrderingAndFilterTests(CatalogTestCase):
    def setUp(self):
        self.payload = snapshot(
            conference('ai-late', edition(2027, {'deadline': '2026-12-20 23:59:59'}), ccf='A', core='A*'),
            conference('ai-soon', edition(2027, {'deadline': '2026-11-02 23:59:59'}), ccf='B', core='A'),
            conference('ai-tbd', edition(2027, {'deadline': None}), ccf='A'),
            conference('nw-old', edition(2026, {'deadline': '2026-01-01 23:59:59'}), category='NW'),
            conference('nw-recent', edition(2026, {'deadline': '2026-09-01 23:59:59'}), category='NW', ccf='C'),
        )
        self.svc = self.service(self.payload, utc(2026, 10, 29))

    def ids(self, **filters) -> list[str]:
        return [item.id for item in self.svc.deadlines(ConferenceFilters(**filters)).items]

    def test_open_soonest_then_tbd_then_recently_closed(self):
        self.assertEqual(self.ids(), ['ai-soon', 'ai-late', 'ai-tbd', 'nw-recent', 'nw-old'])

    def test_rank_filters_or_within_and_across_systems(self):
        self.assertEqual(self.ids(ccf=frozenset({'A', 'B'})), ['ai-soon', 'ai-late', 'ai-tbd'])
        self.assertEqual(self.ids(ccf=frozenset({'A'}), core=frozenset({'A*'})), ['ai-late'])
        self.assertEqual(self.ids(ccf=frozenset({'N'})), ['nw-old'])

    def test_category_status_and_query(self):
        self.assertEqual(self.ids(categories=frozenset({'NW'})), ['nw-recent', 'nw-old'])
        self.assertEqual(self.ids(statuses=frozenset({'open', 'tbd'})), ['ai-soon', 'ai-late', 'ai-tbd'])
        self.assertEqual(self.ids(query='  SOON '), ['ai-soon'])
        self.assertEqual(self.ids(query='ai-late description'), ['ai-late'])

    def test_id_filter_keeps_order_and_empty_set_matches_nothing(self):
        self.assertEqual(self.ids(ids=frozenset({'nw-old', 'ai-late'})), ['ai-late', 'nw-old'])
        self.assertEqual(self.ids(ids=frozenset({'ai-late'}), statuses=frozenset({'closed'})), [])
        self.assertEqual(self.ids(ids=frozenset()), [])

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(UnknownCategoryError):
            self.svc.deadlines(ConferenceFilters(categories=frozenset({'XX'})))

    def test_category_counts_cover_the_whole_snapshot(self):
        counts = {item.id: item.count for item in self.svc.categories().items}
        self.assertEqual(counts, {'AI': 3, 'NW': 2})


class SnapshotTests(CatalogTestCase):
    def test_packaged_snapshot_loads_with_unique_ids(self):
        catalog = load_conference_catalog()
        ids = [record.conference.id for record in catalog.records]
        self.assertGreater(len(ids), 300)
        self.assertEqual(len(ids), len(set(ids)))
        # Same acronym, different venues; and one venue listed under two categories.
        self.assertTrue({'sc-fse', 'se-fse', 'cg-dcc', 'ds-dcc'} <= set(ids))

    def test_duplicate_ids_and_unknown_categories_are_rejected(self):
        with self.assertRaises(ConferenceSnapshotError):
            self.service(snapshot(
                conference('ai-x', edition(2026, {'deadline': None})),
                conference('ai-x', edition(2027, {'deadline': None})),
            ), utc(2026, 1, 1))
        with self.assertRaises(ConferenceSnapshotError):
            self.service(snapshot(
                conference('xx-x', edition(2026, {'deadline': None}), category='XX'),
            ), utc(2026, 1, 1))


class ConferenceApiTests(unittest.TestCase):
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

    def test_list_supports_repeated_filters(self):
        response = self.client.get(
            '/api/v1/conferences',
            params=[('category', 'AI'), ('ccf', 'A'), ('ccf', 'B')],
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()['data']
        self.assertTrue(body['snapshot_id'].startswith('ccfddl-'))
        self.assertEqual(body['data_as_of'], '2026-10-29')
        self.assertEqual(body['total'], len(body['items']))
        self.assertTrue(all(item['category'] == 'AI' for item in body['items']))
        self.assertTrue(all(item['rank']['ccf'] in {'A', 'B'} for item in body['items']))

    def test_categories_endpoint(self):
        response = self.client.get('/api/v1/conferences/categories', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        items = response.json()['data']['items']
        self.assertEqual(len(items), 10)
        self.assertTrue(all(item['count'] > 0 for item in items))

    def test_invalid_filters_are_client_errors(self):
        bad_rank = self.client.get('/api/v1/conferences?ccf=D', headers=self.headers)
        bad_category = self.client.get('/api/v1/conferences?category=XX', headers=self.headers)
        self.assertEqual(bad_rank.status_code, 422)
        self.assertEqual(bad_category.status_code, 422)
        self.assertEqual(bad_category.json()['code'], 20001)

    def test_requires_bff_identity(self):
        self.assertEqual(self.client.get('/api/v1/conferences').status_code, 401)

    def user_headers(self, user_id: str = 'user-a') -> dict:
        return {'x-shenzhi-bff-secret': 'test-secret', 'x-shenzhi-user-id': user_id}

    def test_followed_list_requires_login_and_narrows_to_follows(self):
        anonymous = self.client.get('/api/v1/conferences?followed=true', headers=self.headers)
        self.assertEqual(anonymous.status_code, 401)

        with patch('app.api.conferences.follows.followed_ids', return_value=frozenset({'ai-aaai', 'gone'})) as ids:
            response = self.client.get('/api/v1/conferences?followed=true', headers=self.user_headers())
        ids.assert_awaited_once_with('user-a')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json()['data']['items']], ['ai-aaai'])

    def test_follow_validates_snapshot_id_and_unfollow_always_releases(self):
        with patch('app.api.conferences.follows.follow') as follow:
            ok = self.client.put('/api/v1/conferences/ai-aaai/follow', headers=self.user_headers())
            missing = self.client.put('/api/v1/conferences/no-such/follow', headers=self.user_headers())
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['data'], {'conference_id': 'ai-aaai', 'is_following': True})
        follow.assert_awaited_once_with('user-a', 'ai-aaai')
        self.assertEqual(missing.status_code, 404)

        with patch('app.api.conferences.follows.unfollow') as unfollow:
            released = self.client.delete('/api/v1/conferences/no-such/follow', headers=self.user_headers())
        self.assertEqual(released.json()['data'], {'conference_id': 'no-such', 'is_following': False})
        unfollow.assert_awaited_once_with('user-a', 'no-such')

    def test_follow_requires_login(self):
        response = self.client.put('/api/v1/conferences/ai-aaai/follow', headers=self.headers)
        self.assertEqual(response.status_code, 401)

    def test_snapshot_failure_returns_recoverable_service_error(self):
        with patch(
            'app.api.conferences.service.deadlines',
            side_effect=ConferenceSnapshotError('missing'),
        ):
            response = self.client.get('/api/v1/conferences', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 20004)


if __name__ == '__main__':
    unittest.main()
