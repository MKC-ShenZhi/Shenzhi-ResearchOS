import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from app.main import app
from app.core.identity import require_bff
from app.schemas.knowledge import KnowledgeSearchRequest
from app.integrations.knowledge.adapter import (
    KnowledgeAdapter,
    map_graph,
    map_paper_detail,
    map_search_result,
)
from app.integrations.knowledge.client import KnowledgeBaseClient
from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.services.knowledge import KnowledgeService, KnowledgeServiceError


PAPER_ID = 'paper:17203_aaai:911ff38f19e8'
AUTHOR_ID = 'author:ada-lovelace'
REFERENCE_ID = 'paper:reference:2019'

SEARCH_RESPONSE = {
    'results': [
        {
            'paper_id': PAPER_ID,
            'title': 'GraphMix: Improved Training of GNNs',
            'abstract': 'A real abstract.',
            'conference': 'AAAI',
            'year': 2021,
            'authors': [],
            'keywords': [],
            'subjects': [],
            'score': 0.022,
            'rank': 1,
        },
    ],
    'state': {'step': 0},
    'query_parse': {},
    'query_rewrite': {},
}

DETAIL_RESPONSE = {
    'paper_id': PAPER_ID,
    'title': 'GraphMix: Improved Training of GNNs',
    'authors': ['Ada Lovelace'],
    'year': 2021,
    'venue': 'AAAI',
    'abstract': 'A real abstract.',
    'doi': '',
    'pdf_url': '',
}

GRAPH_RESPONSE = {
    'rootId': PAPER_ID,
    'nodes': [
        {
            'id': PAPER_ID,
            'text': 'GraphMix: Improved Training of GNNs',
            'color': '#fff',
            'borderColor': '#000',
            'data': {'type': 'Paper', 'year': 2021, 'venue': 'AAAI', 'authors': []},
        },
        {
            'id': AUTHOR_ID,
            'text': 'Ada Lovelace',
            'data': {'type': 'Author', 'name': 'Ada Lovelace'},
        },
        {
            'id': REFERENCE_ID,
            'text': 'An Earlier GNN Paper',
            'data': {'type': 'Paper', 'year': 2019},
        },
    ],
    'lines': [
        {
            'from': PAPER_ID,
            'to': AUTHOR_ID,
            'text': 'AUTHORED_BY',
            'data': {
                'type': 'AUTHORED_BY',
                'description': '',
                'weight': 1,
            },
        },
        {
            'from': PAPER_ID,
            'to': REFERENCE_ID,
            'text': 'CITES',
            'data': {'type': 'CITES', 'description': 'reference', 'weight': 1},
        },
    ],
}


class KnowledgeMappingTests(unittest.TestCase):
    def setUp(self):
        self.retrieved_at = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def test_search_mapping_normalizes_external_fields(self):
        result = map_search_result(SEARCH_RESPONSE['results'][0], retrieved_at=self.retrieved_at)
        self.assertEqual(result.id, PAPER_ID)
        self.assertEqual(result.venue, 'AAAI')
        self.assertEqual(result.authors, [])
        self.assertEqual(result.keywords, [])
        self.assertEqual(result.subjects, [])
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.score, 0.022)
        self.assertEqual(result.provenance.provider, 'knowledge-base')
        self.assertEqual(result.provenance.external_id, PAPER_ID)
        naive = map_search_result(
            SEARCH_RESPONSE['results'][0], retrieved_at=datetime(2026, 9, 1)
        )
        self.assertEqual(naive.provenance.retrieved_at.tzinfo, timezone.utc)

    def test_detail_mapping_turns_empty_strings_and_unknown_counts_into_null(self):
        detail = map_paper_detail(DETAIL_RESPONSE, retrieved_at=self.retrieved_at)
        self.assertEqual(detail.id, PAPER_ID)
        self.assertEqual(detail.venue, 'AAAI')
        self.assertEqual(detail.doi, None)
        self.assertEqual(detail.pdf_url, None)
        self.assertIsNone(detail.citation_count)
        self.assertIsNone(detail.reference_count)
        self.assertEqual(detail.keywords, [])
        self.assertEqual(detail.subjects, [])

        empty_counts = copy.deepcopy(DETAIL_RESPONSE)
        empty_counts.update({'citationCount': '', 'referenceCount': ' '})
        normalized = map_paper_detail(empty_counts, retrieved_at=self.retrieved_at)
        self.assertIsNone(normalized.citation_count)
        self.assertIsNone(normalized.reference_count)

    def test_numeric_strings_normalize_without_fabricating_zeroes(self):
        search_item = copy.deepcopy(SEARCH_RESPONSE['results'][0])
        search_item.update({'year': '2021', 'rank': '2', 'score': '0.87'})
        result = map_search_result(search_item, retrieved_at=self.retrieved_at)
        self.assertEqual(result.year, 2021)
        self.assertEqual(result.rank, 2)
        self.assertEqual(result.score, 0.87)

        detail_item = copy.deepcopy(DETAIL_RESPONSE)
        detail_item.update({
            'year': '2021',
            'citationCount': '42',
            'referenceCount': '7',
        })
        detail = map_paper_detail(detail_item, retrieved_at=self.retrieved_at)
        self.assertEqual(detail.year, 2021)
        self.assertEqual(detail.citation_count, 42)
        self.assertEqual(detail.reference_count, 7)

        empty_item = copy.deepcopy(SEARCH_RESPONSE['results'][0])
        empty_item.update({'year': '', 'rank': ' ', 'score': ''})
        empty_result = map_search_result(empty_item, retrieved_at=self.retrieved_at)
        self.assertIsNone(empty_result.year)
        self.assertIsNone(empty_result.rank)
        self.assertIsNone(empty_result.score)

    def test_invalid_numeric_values_are_contract_violations(self):
        invalid_search_values = [
            ('year', '2021.5'),
            ('rank', 'abc'),
            ('score', 'NaN'),
            ('score', float('nan')),
            ('score', 'Infinity'),
            ('score', float('inf')),
        ]
        for field, value in invalid_search_values:
            with self.subTest(field=field, value=value):
                item = copy.deepcopy(SEARCH_RESPONSE['results'][0])
                item[field] = value
                with self.assertRaises(KnowledgeIntegrationError) as caught:
                    map_search_result(item, retrieved_at=self.retrieved_at)
                self.assertEqual(caught.exception.code, 'CONTRACT_VIOLATION')

        for field in ('citationCount', 'referenceCount'):
            with self.subTest(field=field):
                item = copy.deepcopy(DETAIL_RESPONSE)
                item[field] = 'abc'
                with self.assertRaises(KnowledgeIntegrationError) as caught:
                    map_paper_detail(item, retrieved_at=self.retrieved_at)
                self.assertEqual(caught.exception.code, 'CONTRACT_VIOLATION')

    def test_graph_mapping_exposes_open_types_and_cites_direction(self):
        graph = map_graph(GRAPH_RESPONSE, retrieved_at=self.retrieved_at)
        self.assertEqual(graph.root_id, PAPER_ID)
        self.assertEqual(graph.nodes[0].kind, 'Paper')
        self.assertEqual(graph.nodes[1].kind, 'Author')
        edge = graph.edges[0]
        self.assertEqual(edge.source_id, PAPER_ID)
        self.assertEqual(edge.target_id, AUTHOR_ID)
        self.assertEqual(edge.relation, 'AUTHORED_BY')
        cites = next(edge for edge in graph.edges if edge.relation == 'CITES')
        self.assertEqual(cites.source_id, PAPER_ID)
        self.assertEqual(cites.target_id, REFERENCE_ID)
        self.assertNotIn('color', graph.nodes[0].properties)

    def test_graph_mapping_accepts_unknown_node_and_relation_types(self):
        fixture = copy.deepcopy(GRAPH_RESPONSE)
        fixture['nodes'][1]['data']['type'] = 'ExperimentalEntity'
        fixture['lines'][0]['data']['type'] = 'RELATES_TO'
        graph = map_graph(fixture, retrieved_at=self.retrieved_at)
        self.assertEqual(graph.nodes[1].kind, 'ExperimentalEntity')
        self.assertEqual(graph.edges[0].relation, 'RELATES_TO')

    def test_mapping_rejects_missing_required_contract_fields(self):
        with self.assertRaises(KnowledgeIntegrationError) as caught:
            map_search_result({'title': 'missing id'}, retrieved_at=self.retrieved_at)
        self.assertEqual(caught.exception.code, 'CONTRACT_VIOLATION')

    def test_search_request_uses_one_public_spelling_and_rejects_upstream_aliases(self):
        request = KnowledgeSearchRequest.model_validate({
            'query': 'q',
            'topK': 5,
            'yearFrom': 2021,
            'yearTo': 2026,
            'venue': 'AAAI',
        })
        self.assertEqual((request.year_from, request.year_to), (2021, 2026))
        self.assertEqual(request.venue, ['AAAI'])
        for alias in ('top_k', 'year_gte', 'year_lte', 'conference'):
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                KnowledgeSearchRequest.model_validate({'query': 'q', alias: 1})


class FixtureClient:
    async def search(self, request):
        self.search_request = request
        return SEARCH_RESPONSE

    async def paper(self, paper_id):
        self.paper_id = paper_id
        return DETAIL_RESPONSE

    async def graph(self, paper_id, depth):
        self.graph_id = paper_id
        self.depth = depth
        return GRAPH_RESPONSE


class KnowledgeContinuityTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_detail_graph_keep_canonical_id(self):
        client = FixtureClient()
        adapter = KnowledgeAdapter(client)
        search = await adapter.search(KnowledgeSearchRequest(query='graph neural network'))
        self.assertEqual(client.search_request, {
            'query': 'graph neural network',
            'top_k': 10,
        })
        detail = await adapter.paper(search.results[0].id)
        graph = await adapter.graph(search.results[0].id, depth=1)
        self.assertEqual(search.results[0].id, detail.id)
        self.assertEqual(detail.id, graph.root_id)
        self.assertEqual(client.paper_id, PAPER_ID)
        self.assertEqual(client.graph_id, PAPER_ID)
        self.assertEqual(client.depth, 1)

    async def test_adapter_maps_public_filters_before_client_call(self):
        client = FixtureClient()
        adapter = KnowledgeAdapter(client)
        request = KnowledgeSearchRequest.model_validate({
            'query': 'q',
            'topK': 5,
            'yearFrom': 2021,
            'yearTo': 2026,
            'venue': ['AAAI'],
            'author': ['Ada Lovelace'],
            'keyword': ['graph'],
            'subject': ['machine learning'],
        })
        await adapter.search(request)
        self.assertEqual(client.search_request, {
            'query': 'q',
            'top_k': 5,
            'year_gte': 2021,
            'year_lte': 2026,
            'conference': ['AAAI'],
            'author': ['Ada Lovelace'],
            'keyword': ['graph'],
            'subject': ['machine learning'],
        })

    async def test_empty_search_is_a_successful_zero_result_not_an_error(self):
        class EmptyClient(FixtureClient):
            async def search(self, request):
                return {'results': []}

        response = await KnowledgeAdapter(EmptyClient()).search(
            KnowledgeSearchRequest(query='rare query')
        )
        self.assertEqual(response.results, [])


class KnowledgeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_delegates_domain_use_cases_to_adapter(self):
        search_response = object()
        paper_response = object()
        graph_response = object()

        class FixtureAdapter:
            async def search(self, request):
                self.search_request = request
                return search_response

            async def paper(self, paper_id):
                self.paper_id = paper_id
                return paper_response

            async def graph(self, paper_id, *, depth=1):
                self.graph_id = paper_id
                self.depth = depth
                return graph_response

        adapter = FixtureAdapter()
        service = KnowledgeService(adapter)
        request = KnowledgeSearchRequest(query='q')

        self.assertIs(await service.search(request), search_response)
        self.assertIs(await service.get_paper(PAPER_ID), paper_response)
        self.assertIs(await service.get_graph(PAPER_ID, depth=2), graph_response)
        self.assertIs(adapter.search_request, request)
        self.assertEqual(adapter.paper_id, PAPER_ID)
        self.assertEqual(adapter.graph_id, PAPER_ID)
        self.assertEqual(adapter.depth, 2)

    async def test_service_converts_integration_error_to_domain_error(self):
        class FailingAdapter:
            async def search(self, request):
                raise KnowledgeIntegrationError(
                    'TIMEOUT', '知识底座请求超时', True, 504
                )

        with self.assertRaises(KnowledgeServiceError) as caught:
            await KnowledgeService(FailingAdapter()).search(
                KnowledgeSearchRequest(query='q')
            )
        self.assertEqual(caught.exception.error.code, 'TIMEOUT')
        self.assertTrue(caught.exception.error.retryable)
        self.assertEqual(caught.exception.error.request_id, '')
        self.assertEqual(caught.exception.status_code, 504)


class KnowledgeClientTests(unittest.IsolatedAsyncioTestCase):
    def test_client_reads_server_side_configuration(self):
        with patch.dict('os.environ', {
            'KNOWLEDGE_BASE_API_URL': 'https://knowledge.test/',
            'KNOWLEDGE_BASE_TIMEOUT_SEC': '17',
        }):
            client = KnowledgeBaseClient()
        self.assertEqual(client.base_url, 'https://knowledge.test')
        self.assertEqual(client.timeout, 17.0)

    async def test_client_posts_already_adapted_upstream_payload(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=SEARCH_RESPONSE)

        client = KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )
        await client.search({
            'query': 'graph neural network',
            'top_k': 10,
            'year_gte': 2021,
            'year_lte': 2026,
            'conference': ['AAAI'],
            'author': ['Ada Lovelace'],
            'keyword': ['graph'],
            'subject': ['machine learning'],
        })
        self.assertEqual(requests[0].url.path, '/api/retrieval/search')
        self.assertEqual(json.loads(requests[0].content), {
            'query': 'graph neural network',
            'top_k': 10,
            'year_gte': 2021,
            'year_lte': 2026,
            'conference': ['AAAI'],
            'author': ['Ada Lovelace'],
            'keyword': ['graph'],
            'subject': ['machine learning'],
        })

    async def test_client_maps_upstream_statuses_without_leaking_body(self):
        cases = {
            400: ('INVALID_ARGUMENT', False),
            404: ('NOT_FOUND', False),
            429: ('RATE_LIMITED', True),
            500: ('UPSTREAM_UNAVAILABLE', True),
            503: ('UPSTREAM_UNAVAILABLE', True),
        }
        for status, (code, retryable) in cases.items():
            with self.subTest(status=status):
                client = KnowledgeBaseClient(
                    base_url='https://knowledge.test',
                    transport=httpx.MockTransport(
                        lambda request, status=status: httpx.Response(
                            status, json={'error': 'secret-token'}
                        )
                    ),
                )
                with self.assertRaises(KnowledgeIntegrationError) as caught:
                    await client.search({'query': 'q', 'top_k': 1})
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.retryable, retryable)
                self.assertNotIn('secret-token', caught.exception.message)

    async def test_client_maps_timeout_connection_invalid_json_and_contract(self):
        handlers = [
            (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('timed out', request=request)), 'TIMEOUT'),
            (
                lambda request: (_ for _ in ()).throw(
                    httpx.ConnectError('offline', request=request)
                ),
                'UPSTREAM_UNAVAILABLE',
            ),
            (lambda request: httpx.Response(200, text='not-json'), 'CONTRACT_VIOLATION'),
            (lambda request: httpx.Response(200, json={'unexpected': []}), 'CONTRACT_VIOLATION'),
        ]
        for handler, code in handlers:
            with self.subTest(code=code):
                client = KnowledgeBaseClient(
                    base_url='https://knowledge.test', transport=httpx.MockTransport(handler)
                )
                with self.assertRaises(KnowledgeIntegrationError) as caught:
                    await client.search({'query': 'q', 'top_k': 1})
                self.assertEqual(caught.exception.code, code)

    async def test_client_maps_invalid_base_url_to_safe_unavailable_error(self):
        client = KnowledgeBaseClient(base_url='http://example.com:bad')
        with self.assertRaises(KnowledgeIntegrationError) as caught:
            await client.search({'query': 'q', 'top_k': 1})
        self.assertEqual(caught.exception.code, 'UPSTREAM_UNAVAILABLE')
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(caught.exception.status_code, 503)

    async def test_client_rejects_non_http_pdf_urls(self):
        client = KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        )

        with self.assertRaises(KnowledgeIntegrationError) as caught:
            await client.fetch_pdf('file:///tmp/paper.pdf')

        self.assertEqual(caught.exception.code, 'UPSTREAM_UNAVAILABLE')
        self.assertFalse(caught.exception.retryable)

    async def test_client_classifies_pdf_status_and_mime(self):
        cases = [
            (403, 'text/html', 'external_only', False),
            (404, 'text/html', 'unavailable', False),
            (500, 'text/html', 'unavailable', True),
            (200, 'text/html', 'unavailable', False),
        ]
        for status_code, content_type, expected_status, retryable in cases:
            with self.subTest(status=status_code, content_type=content_type):
                client = KnowledgeBaseClient(
                    base_url='https://knowledge.test',
                    transport=httpx.MockTransport(
                        lambda request, status_code=status_code, content_type=content_type: httpx.Response(
                            status_code,
                            headers={'content-type': content_type},
                        )
                    ),
                )
                fetch = await client.fetch_pdf('https://pdf.test/paper.pdf')
                self.assertEqual(fetch.probe.status, expected_status)
                self.assertEqual(fetch.probe.retryable, retryable)
                await fetch.close()

    async def test_client_maps_pdf_timeout_to_retryable_error(self):
        client = KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    httpx.ReadTimeout('timed out', request=request)
                )
            ),
        )

        with self.assertRaises(KnowledgeIntegrationError) as caught:
            await client.fetch_pdf('https://pdf.test/paper.pdf')

        self.assertEqual(caught.exception.code, 'TIMEOUT')
        self.assertTrue(caught.exception.retryable)

    async def test_client_forwards_single_pdf_range_and_keeps_partial_headers(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-99/1000',
                    'accept-ranges': 'bytes',
                    'content-length': '100',
                },
                content=b'%PDF',
            )

        client = KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )

        fetch = await client.fetch_pdf(
            'https://pdf.test/paper.pdf', range_header='bytes=0-99'
        )

        self.assertEqual(requests[0].headers['range'], 'bytes=0-99')
        self.assertEqual(fetch.probe.status_code, 206)
        self.assertEqual(fetch.probe.headers['content-range'], 'bytes 0-99/1000')
        self.assertEqual(fetch.probe.headers['accept-ranges'], 'bytes')
        self.assertEqual(fetch.probe.headers['content-length'], '100')
        await fetch.close()


class KnowledgeApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict('os.environ', {
            'BACKEND_BFF_SECRET': '',
            'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
        })
        self.env.start()
        async def allow_bff():
            return None
        self.allow_bff = allow_bff
        app.dependency_overrides[require_bff] = allow_bff
        self.adapter = FixtureClient()
        self.service = KnowledgeService(KnowledgeAdapter(self.adapter))
        self.service_patch = patch('app.api.knowledge.service', self.service)
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

    async def test_knowledge_search_detail_graph_api_envelope(self):
        search_response = await self.client.post(
            '/api/v1/knowledge/search',
            json={'query': 'graph neural network', 'topK': 10},
        )
        self.assertEqual(search_response.status_code, 200, search_response.text)
        search_data = search_response.json()['data']
        self.assertEqual(search_data['results'][0]['id'], PAPER_ID)
        self.assertEqual(search_data['results'][0]['provenance']['externalId'], PAPER_ID)
        self.assertNotIn('paper_id', search_data['results'][0])
        self.assertNotIn('query_parse', search_data)

        detail_response = await self.client.get(
            '/api/v1/knowledge/paper', params={'paperId': PAPER_ID}
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        self.assertEqual(detail_response.json()['data']['id'], PAPER_ID)
        self.assertIsNone(detail_response.json()['data']['citationCount'])

        graph_response = await self.client.get(
            '/api/v1/knowledge/graph', params={'paperId': PAPER_ID, 'depth': 1}
        )
        self.assertEqual(graph_response.status_code, 200, graph_response.text)
        graph_data = graph_response.json()['data']
        self.assertEqual(graph_data['rootId'], PAPER_ID)
        self.assertEqual(graph_data['edges'][0]['sourceId'], PAPER_ID)

    async def test_api_chain_uses_configured_client_and_never_needs_public_network(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == '/api/retrieval/search':
                return httpx.Response(200, json=SEARCH_RESPONSE)
            if request.url.path == '/api/kg/paper':
                return httpx.Response(200, json=DETAIL_RESPONSE)
            if request.url.path == '/api/kg/graph':
                return httpx.Response(200, json=GRAPH_RESPONSE)
            return httpx.Response(404, json={'error': 'not found'})

        configured = KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test', transport=httpx.MockTransport(handler)
        ))
        configured_service = KnowledgeService(configured)
        self.service_patch.stop()
        self.service_patch = patch('app.api.knowledge.service', configured_service)
        self.service_patch.start()

        search = await self.client.post('/api/v1/knowledge/search', json={'query': 'q'})
        self.assertEqual(search.status_code, 200, search.text)
        paper_id = search.json()['data']['results'][0]['id']
        detail = await self.client.get('/api/v1/knowledge/paper', params={'paperId': paper_id})
        graph = await self.client.get('/api/v1/knowledge/graph', params={'paperId': paper_id})
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(graph.status_code, 200, graph.text)
        self.assertEqual(detail.json()['data']['id'], paper_id)
        self.assertEqual(graph.json()['data']['rootId'], paper_id)
        self.assertEqual(
            [request.url.path for request in requests],
            ['/api/retrieval/search', '/api/kg/paper', '/api/kg/graph'],
        )

    async def test_upstream_error_is_not_silently_returned_as_empty_results(self):
        class FailingAdapter:
            async def search(self, request):
                raise KnowledgeIntegrationError.connection_unavailable()

        self.service_patch.stop()
        self.service_patch = patch(
            'app.api.knowledge.service', KnowledgeService(FailingAdapter())
        )
        self.service_patch.start()
        response = await self.client.post('/api/v1/knowledge/search', json={'query': 'q'})
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body['code'], 'UPSTREAM_UNAVAILABLE')
        self.assertTrue(body['retryable'])
        self.assertTrue(body['requestId'])
        self.assertNotIn('upstream failed', body['message'])

    async def test_invalid_depth_uses_knowledge_error_shape(self):
        response = await self.client.get(
            '/api/v1/knowledge/graph', params={'paperId': PAPER_ID, 'depth': 0}
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body['code'], 'INVALID_ARGUMENT')
        self.assertIn('requestId', body)

    async def test_public_search_rejects_upstream_snake_case_aliases(self):
        response = await self.client.post(
            '/api/v1/knowledge/search', json={'query': 'q', 'top_k': 1}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'INVALID_ARGUMENT')

    async def test_malformed_search_json_is_local_knowledge_error(self):
        response = await self.client.post(
            '/api/v1/knowledge/search',
            content=b'{not-json',
            headers={'content-type': 'application/json'},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'INVALID_ARGUMENT')

    async def test_pdf_endpoint_reports_no_pdf_without_creating_a_proxy_target(self):
        response = await self.client.get(
            '/api/v1/knowledge/paper/pdf', params={'paperId': PAPER_ID}
        )

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')

    async def test_pdf_endpoint_streams_public_pdf_and_uses_paper_id_only(self):
        detail = copy.deepcopy(DETAIL_RESPONSE)
        detail['pdf_url'] = 'https://pdf.test/paper.pdf'
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == '/api/kg/paper':
                return httpx.Response(200, json=detail)
            if request.url.host == 'pdf.test':
                return httpx.Response(
                    200,
                    headers={
                        'content-type': 'application/pdf',
                        'content-length': '8',
                        'accept-ranges': 'bytes',
                        'cache-control': 'public, max-age=60',
                    },
                    content=b'%PDF-1.7',
                )
            return httpx.Response(404)

        service = KnowledgeService(KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )))
        self.service_patch.stop()
        self.service_patch = patch('app.api.knowledge.service', service)
        self.service_patch.start()

        pdf = await self.client.get(
            '/api/v1/knowledge/paper/pdf', params={'paperId': PAPER_ID}
        )
        arbitrary = await self.client.get(
            '/api/v1/knowledge/paper/pdf',
            params={'paperId': PAPER_ID, 'url': 'https://pdf.test/paper.pdf'},
        )

        self.assertEqual(pdf.status_code, 200, pdf.text)
        self.assertEqual(pdf.headers['content-type'], 'application/pdf')
        self.assertEqual(pdf.headers['content-disposition'], 'inline')
        self.assertEqual(pdf.headers['content-length'], '8')
        self.assertEqual(pdf.headers['accept-ranges'], 'bytes')
        self.assertEqual(pdf.headers['cache-control'], 'public, max-age=60')
        self.assertEqual(pdf.content, b'%PDF-1.7')
        self.assertEqual(arbitrary.status_code, 422)
        self.assertEqual(arbitrary.json()['code'], 'INVALID_ARGUMENT')
        self.assertEqual(
            [request.url.host for request in requests],
            ['knowledge.test', 'pdf.test'],
        )

    async def test_pdf_endpoint_forwards_range_and_partial_response_headers(self):
        detail = copy.deepcopy(DETAIL_RESPONSE)
        detail['pdf_url'] = 'https://pdf.test/paper.pdf'
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == '/api/kg/paper':
                return httpx.Response(200, json=detail)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-99/1000',
                    'accept-ranges': 'bytes',
                    'content-length': '100',
                    'cache-control': 'public, max-age=60',
                },
                content=b'%PDF-partial',
            )

        service = KnowledgeService(KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )))
        self.service_patch.stop()
        self.service_patch = patch('app.api.knowledge.service', service)
        self.service_patch.start()

        response = await self.client.get(
            '/api/v1/knowledge/paper/pdf',
            params={'paperId': PAPER_ID},
            headers={'Range': 'bytes=0-99'},
        )

        self.assertEqual(response.status_code, 206, response.text)
        self.assertEqual(response.headers['content-range'], 'bytes 0-99/1000')
        self.assertEqual(response.headers['accept-ranges'], 'bytes')
        self.assertEqual(response.headers['content-length'], '100')
        self.assertEqual(response.headers['cache-control'], 'public, max-age=60')
        self.assertEqual(response.content, b'%PDF-partial')
        self.assertEqual(requests[-1].headers['range'], 'bytes=0-99')

    async def test_pdf_endpoint_keeps_full_response_when_upstream_ignores_range(self):
        detail = copy.deepcopy(DETAIL_RESPONSE)
        detail['pdf_url'] = 'https://pdf.test/paper.pdf'
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == '/api/kg/paper':
                return httpx.Response(200, json=detail)
            return httpx.Response(
                200,
                headers={
                    'content-type': 'application/pdf',
                    'content-length': '12',
                    'accept-ranges': 'bytes',
                },
                content=b'%PDF-complete',
            )

        service = KnowledgeService(KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )))
        self.service_patch.stop()
        self.service_patch = patch('app.api.knowledge.service', service)
        self.service_patch.start()

        response = await self.client.get(
            '/api/v1/knowledge/paper/pdf',
            params={'paperId': PAPER_ID},
            headers={'Range': 'bytes=0-99'},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-length'], '12')
        self.assertNotIn('content-range', response.headers)
        self.assertEqual(response.content, b'%PDF-complete')
        self.assertEqual(requests[-1].headers['range'], 'bytes=0-99')

    async def test_pdf_endpoint_classifies_openreview_style_access_denial(self):
        detail = copy.deepcopy(DETAIL_RESPONSE)
        detail['pdf_url'] = 'https://openreview.test/pdf?id=paper'

        def handler(request):
            if request.url.path == '/api/kg/paper':
                return httpx.Response(200, json=detail)
            return httpx.Response(403, text='<html>login required</html>')

        service = KnowledgeService(KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )))
        self.service_patch.stop()
        self.service_patch = patch('app.api.knowledge.service', service)
        self.service_patch.start()

        pdf = await self.client.get(
            '/api/v1/knowledge/paper/pdf', params={'paperId': PAPER_ID}
        )

        self.assertEqual(pdf.status_code, 403)
        self.assertEqual(pdf.json()['code'], 'UPSTREAM_UNAVAILABLE')
        self.assertNotEqual(pdf.headers.get('content-type'), 'application/pdf')

    async def test_pdf_endpoint_marks_timeout_retryable(self):
        detail = copy.deepcopy(DETAIL_RESPONSE)
        detail['pdf_url'] = 'https://pdf.test/paper.pdf'

        def handler(request):
            if request.url.path == '/api/kg/paper':
                return httpx.Response(200, json=detail)
            raise httpx.ReadTimeout('timed out', request=request)

        service = KnowledgeService(KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(handler),
        )))
        self.service_patch.stop()
        self.service_patch = patch('app.api.knowledge.service', service)
        self.service_patch.start()

        response = await self.client.get(
            '/api/v1/knowledge/paper/pdf', params={'paperId': PAPER_ID}
        )

        self.assertEqual(response.status_code, 504, response.text)
        self.assertEqual(response.json()['code'], 'TIMEOUT')
        self.assertTrue(response.json()['retryable'])


if __name__ == '__main__':
    unittest.main()
