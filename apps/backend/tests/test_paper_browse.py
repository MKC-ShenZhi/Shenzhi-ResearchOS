"""Conference browsing exercises the same API/service/integration as search."""

import copy
import unittest
from unittest.mock import patch

import httpx

from app.core.identity import require_bff
from app.integrations.knowledge.adapter import KnowledgeAdapter
from app.integrations.knowledge.client import KnowledgeBaseClient
from app.main import app
from app.services.knowledge.service import KnowledgeService


VENUES = [
    {'conference': 'AAAI', 'count': '31', 'years': [2022, '2026', 2022],
     'minYear': 2016, 'maxYear': 2026, 'yearCount': 99, 'trackCount': 4},
    {'conference': 'AAAI alias', 'count': 2, 'years': [2021]},
]
PAPER_ID = 'paper:opaque/with%characters:abc'
PAPER = {'id': 1234, 'paper_id': PAPER_ID, 'title': 'A real paper',
         'authors': ['Ada'], 'conference': 'AAAI', 'year': '2026', 'source_file': 'internal'}


class PaperBrowseApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.venues = copy.deepcopy(VENUES)
        self.page = {'items': [copy.deepcopy(PAPER)], 'total': '31', 'limit': 20, 'offset': 0}
        self.failure = None

        def handler(request):
            self.requests.append(request)
            if self.failure:
                return httpx.Response(self.failure, json={'secret': 'do-not-expose'})
            if request.url.path == '/api/papers/venues':
                return httpx.Response(200, json=self.venues)
            if request.url.path == '/api/papers':
                return httpx.Response(200, json=self.page)
            if request.url.path == '/api/kg/paper':
                return httpx.Response(200, json=PAPER)
            return httpx.Response(404)

        self.service = KnowledgeService(KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test', transport=httpx.MockTransport(handler),
        )))
        self.service_patch = patch('app.api.knowledge.service', self.service)
        self.service_patch.start()

        async def allow_bff():
            return None

        app.dependency_overrides[require_bff] = allow_bff
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.pop(require_bff, None)
        self.service_patch.stop()

    async def test_directory_adapts_real_years_without_merging_names_or_filling_gaps(self):
        response = await self.client.get('/api/v1/knowledge/conferences')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data'], {'items': [
            {'name': 'AAAI', 'paperCount': 31, 'years': [2026, 2022], 'yearCount': 2},
            {'name': 'AAAI alias', 'paperCount': 2, 'years': [2021], 'yearCount': 1},
        ]})
        self.assertEqual(self.requests[0].url.path, '/api/papers/venues')

    async def test_browse_without_keyword_uses_paper_id_and_matches_detail(self):
        response = await self.client.get('/api/v1/knowledge/papers', params={
            'conference': 'AAAI', 'year': 2026, 'limit': 20, 'offset': 0,
        })
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()['data']
        self.assertEqual((data['total'], data['limit'], data['offset']), (31, 20, 0))
        self.assertEqual(data['results'][0]['id'], PAPER_ID)
        self.assertEqual(data['results'][0]['venue'], 'AAAI')
        self.assertNotIn('source_file', data['results'][0])
        self.assertNotIn('paper_id', data['results'][0])
        self.assertIsNone(data['results'][0]['score'])
        self.assertEqual(dict(self.requests[0].url.params), {
            'conference': 'AAAI', 'year': '2026', 'limit': '20', 'offset': '0',
        })
        detail = await self.client.get('/api/v1/knowledge/paper', params={'paperId': data['results'][0]['id']})
        self.assertEqual(detail.json()['data']['id'], PAPER_ID)

    async def test_deep_pagination_forwards_offset_without_search_window_limit(self):
        self.page.update({'offset': 1200, 'items': []})
        response = await self.client.get('/api/v1/knowledge/papers', params={
            'conference': 'AAAI alias', 'year': 2021, 'offset': 1200,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requests[0].url.params['offset'], '1200')
        self.assertEqual(self.requests[0].url.params['conference'], 'AAAI alias')

    async def test_empty_directory_and_empty_paper_page_are_successes(self):
        self.venues = []
        self.page.update({'items': [], 'total': 0})
        response = await self.client.get('/api/v1/knowledge/conferences')
        self.assertEqual(response.json()['data']['items'], [])
        response = await self.client.get('/api/v1/knowledge/papers?conference=AAAI&year=2026')
        self.assertEqual(response.json()['data']['results'], [])
        self.assertEqual(response.json()['data']['total'], 0)

    async def test_invalid_arguments_never_reach_upstream(self):
        for params in ({}, {'conference': '', 'year': 2026}, {'conference': 'AAAI'},
                       {'conference': 'AAAI', 'year': 'x'}, {'conference': 'AAAI', 'year': 0},
                       {'conference': 'AAAI', 'year': 2026, 'limit': 101},
                       {'conference': 'AAAI', 'year': 2026, 'offset': -1}):
            with self.subTest(params=params):
                response = await self.client.get('/api/v1/knowledge/papers', params=params)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.requests, [])

    async def test_numeric_database_id_is_never_a_fallback(self):
        del self.page['items'][0]['paper_id']
        response = await self.client.get('/api/v1/knowledge/papers?conference=AAAI&year=2026')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['code'], 'CONTRACT_VIOLATION')

    async def test_malformed_directory_does_not_masquerade_as_empty(self):
        for invalid in ({'items': []}, [{'conference': '', 'count': 3, 'years': []}],
                        [{'conference': 'AAAI', 'count': -1, 'years': [2026]}],
                        [{'conference': 'AAAI', 'count': 1, 'years': ['invalid']}],
                        [{'conference': 'AAAI', 'count': 1}]):
            with self.subTest(invalid=invalid):
                self.venues = invalid
                response = await self.client.get('/api/v1/knowledge/conferences')
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()['code'], 'CONTRACT_VIOLATION')

    async def test_pagination_contract_must_match_requested_page(self):
        for invalid in ({'total': -1}, {'offset': 1}, {'limit': 10}, {'total': 'invalid'}):
            with self.subTest(invalid=invalid):
                with patch.dict(self.page, invalid):
                    response = await self.client.get('/api/v1/knowledge/papers?conference=AAAI&year=2026')
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()['code'], 'CONTRACT_VIOLATION')

    async def test_upstream_failure_preserves_safe_error_and_request_id(self):
        for status, expected in ((429, 'RATE_LIMITED'), (503, 'UPSTREAM_UNAVAILABLE')):
            self.failure = status
            for path in ('/api/v1/knowledge/conferences', '/api/v1/knowledge/papers?conference=AAAI&year=2026'):
                response = await self.client.get(path)
                self.assertEqual(response.json()['code'], expected)
                self.assertTrue(response.json()['retryable'])
                self.assertTrue(response.json()['requestId'])
                self.assertNotIn('do-not-expose', response.text)


if __name__ == '__main__':
    unittest.main()
