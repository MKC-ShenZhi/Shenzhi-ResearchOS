import unittest
from unittest.mock import patch

import httpx

from app.core.identity import require_bff
from app.integrations.knowledge.adapter import (
    KnowledgeAdapter,
    map_scholar_detail,
    map_scholar_summary,
)
from app.integrations.knowledge.client import KnowledgeBaseClient
from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.main import app
from app.schemas.knowledge import ScholarSearchRequest
from app.services.knowledge.service import KnowledgeService, KnowledgeServiceError


SCHOLAR_ID = 'author:legacy:d1381dc0b07a0347ebb834d5'
PAPER_ID = 'paper:opaque:1'
SCHOLAR_SEARCH_RESPONSE = {
    'results': [{
        'scholar_id': SCHOLAR_ID,
        'name': 'Geoffrey Hinton',
        'paper_count': 7,
    }],
    'query': 'Hinton',
}
SCHOLAR_DETAIL_RESPONSE = {
    'scholar_id': SCHOLAR_ID,
    'name': 'Geoffrey Hinton',
    'paper_count': 7,
    'years': [2021, '2022'],
    'conferences': ['NeurIPS 2021'],
    'topics': ['neural networks'],
    'funding': [],
    'institutions': [],
    'coauthors': [{
        'scholar_id': 'author:opaque:coauthor',
        'name': 'Coauthor',
    }],
    'papers': [{
        'paper_id': PAPER_ID,
        'title': 'A real paper',
        'year': '2021',
    }],
}
RELATED_PAPER_RESPONSE = {
    'results': [{
        'paper_id': PAPER_ID,
        'title': 'A real paper',
        'abstract': None,
        'conference': 'NeurIPS',
        'year': 2024,
        'authors': ['Ada Lovelace'],
        'keywords': [],
        'subjects': ['graph'],
        'score': 0.2,
        'rank': 1,
        # Upstream-only diagnostics must not escape the adapter.
        'source_scores': {'bm25_raw': 1.0},
        'retrieval_mode': 'bm25+dense',
        'funding': ['NSF'],
    }],
    'state': {},
    'query_parse': {},
    'query_rewrite': {},
}


class KnowledgeEntityMappingTests(unittest.TestCase):
    def test_scholar_search_mapping_owns_names_and_preserves_opaque_id(self):
        result = map_scholar_summary(SCHOLAR_SEARCH_RESPONSE['results'][0])
        self.assertEqual(result.id, SCHOLAR_ID)
        self.assertEqual(result.name, 'Geoffrey Hinton')
        self.assertEqual(result.paper_count, 7)
        self.assertEqual(result.provenance.external_id, SCHOLAR_ID)

    def test_scholar_detail_mapping_maps_supported_nested_fields(self):
        result = map_scholar_detail(SCHOLAR_DETAIL_RESPONSE)
        self.assertEqual(result.id, SCHOLAR_ID)
        self.assertEqual(result.years, [2021, 2022])
        self.assertEqual(result.coauthors[0].id, 'author:opaque:coauthor')
        self.assertEqual(result.papers[0].id, PAPER_ID)
        self.assertEqual(result.papers[0].year, 2021)

    def test_scholar_detail_missing_optional_fields_become_empty_lists(self):
        result = map_scholar_detail({
            'scholar_id': SCHOLAR_ID,
            'name': 'Geoffrey Hinton',
            'paper_count': '0',
        })
        self.assertEqual(result.paper_count, 0)
        for field in (
            result.years,
            result.conferences,
            result.topics,
            result.funding,
            result.institutions,
            result.coauthors,
            result.papers,
        ):
            self.assertEqual(field, [])

    def test_scholar_contract_violation_is_not_silently_normalized(self):
        invalid = {**SCHOLAR_DETAIL_RESPONSE, 'coauthors': [{'scholar_id': 'missing-name'}]}
        with self.assertRaises(KnowledgeIntegrationError) as caught:
            map_scholar_detail(invalid)
        self.assertEqual(caught.exception.code, 'CONTRACT_VIOLATION')


class EntityFixtureClient:
    async def search_scholars(self, query, *, limit, offset):
        self.scholar_search = (query, limit, offset)
        return SCHOLAR_SEARCH_RESPONSE

    async def scholar(self, scholar_id):
        self.scholar_id = scholar_id
        return SCHOLAR_DETAIL_RESPONSE

    async def search_by_subject(self, subject, *, top_k):
        self.subject_search = (subject, top_k)
        return RELATED_PAPER_RESPONSE

    async def search_by_funding(self, funding, *, top_k):
        self.funding_search = (funding, top_k)
        return RELATED_PAPER_RESPONSE


class KnowledgeEntityAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_scholar_search_and_detail_mapping(self):
        client = EntityFixtureClient()
        adapter = KnowledgeAdapter(client)
        search = await adapter.search_scholars(ScholarSearchRequest(
            query='Hinton', limit=5, offset=2
        ))
        detail = await adapter.scholar(SCHOLAR_ID)
        self.assertEqual(client.scholar_search, ('Hinton', 5, 2))
        self.assertEqual(search.results[0].id, SCHOLAR_ID)
        self.assertEqual(client.scholar_id, SCHOLAR_ID)
        self.assertEqual(detail.papers[0].id, PAPER_ID)

    async def test_subject_query_maps_paper_results_and_omits_upstream_fields(self):
        client = EntityFixtureClient()
        result = await KnowledgeAdapter(client).search_by_subject('graph', top_k=7)
        self.assertEqual(client.subject_search, ('graph', 7))
        self.assertEqual(result.results[0].id, PAPER_ID)
        self.assertFalse(hasattr(result.results[0], 'source_scores'))
        self.assertFalse(hasattr(result.results[0], 'funding'))

    async def test_subject_empty_result_is_success(self):
        class EmptyClient(EntityFixtureClient):
            async def search_by_subject(self, subject, *, top_k):
                return {'results': []}

        result = await KnowledgeAdapter(EmptyClient()).search_by_subject('rare')
        self.assertEqual(result.results, [])

    async def test_funding_uses_paper_contract_not_a_fabricated_entity(self):
        client = EntityFixtureClient()
        result = await KnowledgeAdapter(client).search_by_funding('NSF', top_k=3)
        self.assertEqual(client.funding_search, ('NSF', 3))
        self.assertEqual([paper.id for paper in result.results], [PAPER_ID])

    async def test_scholar_upstream_error_maps_through_service(self):
        class FailingAdapter:
            async def search_scholars(self, request):
                raise KnowledgeIntegrationError.timeout()

        with self.assertRaises(KnowledgeServiceError) as caught:
            await KnowledgeService(FailingAdapter()).search_scholars(
                ScholarSearchRequest(query='Hinton')
            )
        self.assertEqual(caught.exception.error.code, 'TIMEOUT')
        self.assertTrue(caught.exception.error.retryable)
        self.assertEqual(caught.exception.status_code, 504)

    async def test_upstream_failure_maps_through_service(self):
        class FailingAdapter:
            async def search_by_subject(self, subject, *, top_k):
                raise KnowledgeIntegrationError.connection_unavailable()

        with self.assertRaises(KnowledgeServiceError) as caught:
            await KnowledgeService(FailingAdapter()).search_by_subject('graph')
        self.assertEqual(caught.exception.error.code, 'UPSTREAM_UNAVAILABLE')
        self.assertEqual(caught.exception.status_code, 503)


class KnowledgeEntityClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_uses_documented_get_endpoints_and_query_names(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path.endswith('/search/by-subject'):
                return httpx.Response(200, json=RELATED_PAPER_RESPONSE)
            if request.url.path.endswith('/search/by-funding'):
                return httpx.Response(200, json=RELATED_PAPER_RESPONSE)
            if request.url.path.endswith('/scholars/search'):
                return httpx.Response(200, json=SCHOLAR_SEARCH_RESPONSE)
            return httpx.Response(200, json=SCHOLAR_DETAIL_RESPONSE)

        client = KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )
        await client.search_scholars('Hinton', limit=20, offset=0)
        await client.scholar(SCHOLAR_ID)
        await client.search_by_subject('graph', top_k=10)
        await client.search_by_funding('NSF', top_k=10)

        self.assertEqual([request.url.path for request in requests], [
            '/api/retrieval/scholars/search',
            f'/api/retrieval/scholars/{SCHOLAR_ID}',
            '/api/retrieval/search/by-subject',
            '/api/retrieval/search/by-funding',
        ])
        self.assertEqual(dict(requests[0].url.params), {
            'q': 'Hinton', 'limit': '20', 'offset': '0'
        })
        self.assertEqual(dict(requests[2].url.params), {
            'subject': 'graph', 'top_k': '10'
        })
        self.assertEqual(dict(requests[3].url.params), {
            'funding': 'NSF', 'top_k': '10'
        })

    async def test_client_rejects_invalid_json_and_contract(self):
        cases = [
            lambda request: httpx.Response(200, text='not-json'),
            lambda request: httpx.Response(200, json={'results': 'not-a-list'}),
        ]
        for handler in cases:
            with self.subTest(handler=handler):
                client = KnowledgeBaseClient(
                    base_url='https://knowledge.test',
                    transport=httpx.MockTransport(handler),
                )
                with self.assertRaises(KnowledgeIntegrationError) as caught:
                    await client.search_scholars('Hinton')
                self.assertEqual(caught.exception.code, 'CONTRACT_VIOLATION')

    async def test_client_maps_upstream_status_for_new_endpoints(self):
        client = KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, json={'detail': 'secret'})
            ),
        )
        with self.assertRaises(KnowledgeIntegrationError) as caught:
            await client.search_by_subject('graph')
        self.assertEqual(caught.exception.code, 'RATE_LIMITED')
        self.assertTrue(caught.exception.retryable)


class KnowledgeEntityApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict('os.environ', {
            'BACKEND_BFF_SECRET': '',
            'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
        })
        self.env.start()

        async def allow_bff():
            return None

        app.dependency_overrides[require_bff] = allow_bff
        self.adapter = EntityFixtureClient()
        self.service_patch = patch(
            'app.api.knowledge.service',
            KnowledgeService(KnowledgeAdapter(self.adapter)),
        )
        self.service_patch.start()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test',
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.pop(require_bff, None)
        self.service_patch.stop()
        self.env.stop()

    async def test_new_routes_expose_only_shenzhi_contract(self):
        scholar_search = await self.client.get(
            '/api/v1/knowledge/scholars/search',
            params={'q': 'Hinton', 'limit': 20, 'offset': 0},
        )
        self.assertEqual(scholar_search.status_code, 200, scholar_search.text)
        summary = scholar_search.json()['data']['results'][0]
        self.assertEqual(summary['id'], SCHOLAR_ID)
        self.assertEqual(summary['paperCount'], 7)
        self.assertNotIn('scholar_id', summary)

        scholar_detail = await self.client.get(
            f'/api/v1/knowledge/scholars/{SCHOLAR_ID}'
        )
        self.assertEqual(scholar_detail.status_code, 200, scholar_detail.text)
        self.assertEqual(scholar_detail.json()['data']['papers'][0]['id'], PAPER_ID)

        subject = await self.client.get(
            '/api/v1/knowledge/subjects/search',
            params={'subject': 'graph', 'topK': 10},
        )
        funding = await self.client.get(
            '/api/v1/knowledge/funding/search',
            params={'funding': 'NSF', 'topK': 10},
        )
        self.assertEqual(subject.status_code, 200, subject.text)
        self.assertEqual(funding.status_code, 200, funding.text)
        self.assertEqual(subject.json()['data']['results'][0]['id'], PAPER_ID)
        self.assertEqual(funding.json()['data']['results'][0]['id'], PAPER_ID)
        self.assertNotIn('source_scores', subject.json()['data']['results'][0])

    async def test_new_routes_validate_blank_or_out_of_range_queries(self):
        cases = [
            ('/api/v1/knowledge/scholars/search', {'q': ' '}),
            ('/api/v1/knowledge/subjects/search', {'subject': ' ', 'topK': 10}),
            ('/api/v1/knowledge/funding/search', {'funding': 'NSF', 'topK': 21}),
        ]
        for path, params in cases:
            with self.subTest(path=path):
                response = await self.client.get(path, params=params)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['code'], 'INVALID_ARGUMENT')


if __name__ == '__main__':
    unittest.main()
