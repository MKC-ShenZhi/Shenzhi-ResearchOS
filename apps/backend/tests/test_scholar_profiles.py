"""Product Scholar V2 contract tests; fixtures do not imply live upstream acceptance."""
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, call, patch
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from app.api.knowledge import router
from app.core.identity import require_bff
from app.integrations.knowledge.adapter import KnowledgeAdapter, map_scholar_profile
from app.integrations.knowledge.client import KnowledgeBaseClient
from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.schemas.knowledge import ScholarSearchRequest
from app.services.knowledge.cache import ScholarBrowseCache
from app.services.knowledge.service import KnowledgeService, KnowledgeServiceError

ID = 'author:legacy/何?name=%252F/papers'
PROFILE = {
    'scholar_id': ID, 'name_en': 'Marcel Kockmann', 'name_zh': None,
    'avatar_path': None, 'affiliations': [], 'bio_zh': None, 'bio_en': None,
    'metrics': {'paper_count': 11, 'citation_count': None},
    'annual_citations': [], 'updated_at': None,
    'citation_meta': {'source': None, 'coverage': None, 'as_of': None},
}
PAPER = {
    'id': 85646, 'paper_id': 'paper:alam17b_interspeech_2017_isca:81a0a1497158',
    'title': 'Speaker Verification Under Adverse Conditions Using i-Vector Adaptation and Neural Networks',
    'authors': ['Jahangir Alam', 'Marcel Kockmann'], 'year': 2017,
    'conference': 'INTERSPEECH', 'doi': '10.21437/INTERSPEECH.2017-1240',
    'pdf_url': 'https://www.isca-archive.org/interspeech_2017/alam17b_interspeech.pdf',
    'image_id': '/images/papers/alam17b.webp',
    'topics': [{'id': 'topic:speech', 'nameEn': 'Speech recognition'}],
    'external': False,
}


class ProductMappingTests(unittest.TestCase):
    def test_null_zero_and_source_metrics_stay_distinct(self):
        source = {**PROFILE, 'metrics': {'paper_count': 0, 'citation_count': None}, 'works_count': 900}
        mapped = map_scholar_profile(source)
        self.assertEqual(mapped.metrics.paper_count, 0)
        self.assertIsNone(mapped.metrics.citation_count)
        self.assertNotIn('works_count', mapped.model_dump())
        self.assertEqual(map_scholar_profile({'scholar_id': ID}).name_en, None)
        self.assertIsNone(map_scholar_profile({'scholar_id': ID}).metrics)

    def test_sparse_annual_data_and_institution_do_not_invent_roles(self):
        mapped = map_scholar_profile({**PROFILE,
            'annual_citations': [{'year': 2010, 'count': 0}, {'year': 2024, 'count': None}],
            'affiliations': [{'institution': 'Example University'}],
        })
        self.assertEqual([item.count for item in mapped.annual_citations], [0, None])
        self.assertIsNone(mapped.affiliations[0].position)
        self.assertIsNone(mapped.bio_en)

    def test_invalid_counts_ids_nested_fields_and_duplicates_are_classified(self):
        for changes in (
            {'scholar_id': ''}, {'metrics': {'paper_count': -1}},
            {'metrics': {'citation_count': True}}, {'metrics': {'paper_count': '11'}},
            {'annual_citations': [{'year': 2024, 'count': -2}]},
            {'annual_citations': [{'year': 2024, 'count': 2}, {'year': 2024, 'count': 3}]},
            {'affiliations': ['invented role']},
        ):
            with self.subTest(changes=changes), self.assertRaises(KnowledgeIntegrationError) as ctx:
                map_scholar_profile({**PROFILE, **changes})
            self.assertEqual(ctx.exception.code, 'CONTRACT_VIOLATION')

    def test_raw_openalex_is_not_a_product_profile_and_relative_avatar_is_not_rebased(self):
        with self.assertRaises(KnowledgeIntegrationError):
            map_scholar_profile({'id': 'https://openalex.org/A1', 'display_name': 'Person'})
        self.assertIsNone(map_scholar_profile({**PROFILE, 'avatar_path': '/avatars/1.png'}).avatar_path)


class FixtureClient:
    async def browse_scholar_profiles(self, *, limit, offset):
        return {
            'items': [{
                **deepcopy(PROFILE),
                'topics': ['Machine learning'],
                'metrics': {'source_work_count': 17, 'paper_count': 2, 'h_index': 5, 'i10_index': 0},
                'employment': [{'organization': 'Example University', 'start_date': '2024-06'}],
                'avatar_path': '/images/scholars_example/avatar.jpg',
            }],
            'limit': limit, 'offset': offset, 'total': 3,
        }

    async def search_scholar_profiles(self, query, *, limit, offset):
        self.search_args = query, limit, offset
        return {'items': [deepcopy(PROFILE)], 'limit': limit, 'offset': offset}

    async def scholar_profile(self, scholar_id):
        return {**deepcopy(PROFILE), 'scholar_id': scholar_id}

    async def scholar_papers(self, scholar_id, *, limit, offset):
        return {'items': [deepcopy(PAPER)] if offset == 0 else [], 'total': 1, 'limit': limit, 'offset': offset}


class ProductAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_browse_reuses_each_page_until_expiry(self):
        now = 0.0
        cache = ScholarBrowseCache(ttl_seconds=300, max_entries=128, clock=lambda: now)
        client = FixtureClient()
        client.browse_scholar_profiles = AsyncMock(wraps=client.browse_scholar_profiles)
        service = KnowledgeService(KnowledgeAdapter(client), scholar_browse_cache=cache)

        for _ in range(2):
            for limit, offset in ((1, 0), (1, 1), (2, 0)):
                page = await service.browse_scholar_profiles(limit=limit, offset=offset)
                self.assertEqual((page.limit, page.offset), (limit, offset))
        self.assertEqual(client.browse_scholar_profiles.await_args_list, [
            call(limit=1, offset=0), call(limit=1, offset=1), call(limit=2, offset=0),
        ])

        now = 300.0
        await service.browse_scholar_profiles(limit=1, offset=0)
        self.assertEqual(client.browse_scholar_profiles.await_count, 4)

    async def test_pagination_without_total_and_query_without_legacy_alias(self):
        client = FixtureClient()
        service = KnowledgeService(KnowledgeAdapter(client))
        page = await service.search_scholar_profiles(ScholarSearchRequest(query=' 何恺明 ', limit=1, offset=2))
        self.assertEqual(client.search_args, ('何恺明', 1, 2))
        self.assertTrue(page.has_more)
        self.assertIsNone(page.total)
        page = await service.search_scholar_profiles(ScholarSearchRequest(query='Marcel', limit=20))
        self.assertFalse(page.has_more)

    async def test_papers_map_platform_id_never_database_row_id_and_support_empty_page(self):
        adapter = KnowledgeAdapter(FixtureClient())
        page = await adapter.scholar_papers(ID, limit=2)
        self.assertEqual(page.items[0].id, PAPER['paper_id'])
        self.assertEqual(page.items[0].venue, 'INTERSPEECH')
        self.assertEqual(page.items[0].image_id, PAPER['image_id'])
        self.assertEqual(page.items[0].topics[0].name_en, 'Speech recognition')
        self.assertTrue(page.items[0].platform_detail)
        self.assertEqual((await adapter.scholar_papers(ID, limit=2, offset=2)).items, [])

    async def test_external_or_unknown_papers_do_not_gain_internal_navigation(self):
        class ExternalClient(FixtureClient):
            async def scholar_papers(self, scholar_id, *, limit, offset):
                body = await super().scholar_papers(scholar_id, limit=limit, offset=offset)
                body['items'][0]['external'] = True
                return body
        self.assertFalse((await KnowledgeAdapter(ExternalClient()).scholar_papers(ID)).items[0].platform_detail)

    async def test_wrong_page_or_identity_is_contract_error(self):
        class BadPage(FixtureClient):
            async def search_scholar_profiles(self, query, *, limit, offset):
                return {'items': [], 'limit': limit, 'offset': offset + 1}
        with self.assertRaises(KnowledgeIntegrationError):
            await KnowledgeAdapter(BadPage()).search_scholar_profiles(ScholarSearchRequest(query='x'))
        class BadIdentity(FixtureClient):
            async def scholar_profile(self, scholar_id):
                return PROFILE
        with self.assertRaises(KnowledgeIntegrationError):
            await KnowledgeAdapter(BadIdentity()).scholar_profile('other-id')

    async def test_transport_uses_product_paths_and_preserves_encoded_id(self):
        seen = []
        def handler(request):
            seen.append(request)
            if request.url.path == '/api/v1/scholars':
                return httpx.Response(200, json={'items': [], 'limit': 2, 'offset': 4, 'total': 4})
            if request.url.path.endswith('/search'):
                return httpx.Response(200, json={'items': [], 'limit': 2, 'offset': 4})
            if request.url.raw_path.split(b'?')[0].endswith(b'/papers'):
                return httpx.Response(200, json={'items': [], 'total': 0, 'limit': 2, 'offset': 0})
            return httpx.Response(200, json=PROFILE)
        adapter = KnowledgeAdapter(KnowledgeBaseClient(base_url='https://example.test', transport=httpx.MockTransport(handler)))
        await adapter.search_scholar_profiles(ScholarSearchRequest(query='何恺明', limit=2, offset=4))
        await adapter.scholar_profile(ID)
        await adapter.scholar_papers(ID, limit=2)
        await adapter.browse_scholar_profiles(limit=2, offset=4)
        self.assertEqual(seen[0].url.params['q'], '何恺明')
        self.assertEqual(seen[0].url.path, '/api/v1/scholars/search')
        self.assertIn(quote(ID, safe=''), str(seen[1].url))
        self.assertTrue(seen[2].url.path.endswith('/papers'))
        self.assertEqual(seen[3].url.path, '/api/v1/scholars')
        self.assertEqual(dict(seen[3].url.params), {'limit': '2', 'offset': '4'})

    async def test_avatar_fetch_only_accepts_scholar_image_paths_and_types(self):
        seen = []

        def handler(request):
            seen.append(request.url.path)
            media_type = 'image/jpeg' if request.url.path.endswith('avatar.jpg') else 'text/html'
            return httpx.Response(200, content=b'image', headers={'content-type': media_type})

        client = KnowledgeBaseClient(base_url='https://example.test', transport=httpx.MockTransport(handler))
        path = '/images/scholars_example/avatar.jpg'
        self.assertEqual(await client.scholar_avatar(path), (b'image', 'image/jpeg'))
        for invalid in ('//other.test/avatar.jpg', '/images/scholars_example/../avatar.jpg',
                        '/images/scholars_example/%2e%2e.jpg', '/api/v1/scholars'):
            with self.subTest(invalid=invalid), self.assertRaises(KnowledgeIntegrationError):
                await client.scholar_avatar(invalid)
        self.assertEqual(seen, [path])
        with self.assertRaises(KnowledgeIntegrationError):
            await client.scholar_avatar('/images/scholars_example/not_an_image.jpg')

    async def test_timeout_network_status_and_invalid_json_map_through_service(self):
        for failure, code, retryable in [
            (httpx.ReadTimeout('private'), 'TIMEOUT', True),
            (httpx.ConnectError('private'), 'UPSTREAM_UNAVAILABLE', True),
            (404, 'NOT_FOUND', False), (429, 'RATE_LIMITED', True),
            (503, 'UPSTREAM_UNAVAILABLE', True), ('invalid', 'CONTRACT_VIOLATION', False),
        ]:
            def handler(request):
                if isinstance(failure, Exception):
                    raise failure
                if failure == 'invalid':
                    return httpx.Response(200, text='not json')
                return httpx.Response(failure, json={'secret': 'not exposed'})
            service = KnowledgeService(KnowledgeAdapter(KnowledgeBaseClient(
                base_url='https://example.test', transport=httpx.MockTransport(handler),
            )))
            with self.subTest(failure=failure), self.assertRaises(KnowledgeServiceError) as ctx:
                await service.get_scholar_profile(ID)
            self.assertEqual(ctx.exception.error.code, code)
            self.assertEqual(ctx.exception.error.retryable, retryable)
            self.assertNotIn('private', str(ctx.exception))


class ProductApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_bff] = lambda: None
        self.patch = patch('app.api.knowledge.service', KnowledgeService(KnowledgeAdapter(FixtureClient())))
        self.patch.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        self.patch.stop()

    async def test_encoded_id_profile_and_papers_round_trip(self):
        path = '/api/v1/knowledge/scholar-profiles/' + quote(ID, safe='')
        detail = await self.client.get(path)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()['data']['scholar_id'], ID)
        papers = await self.client.get('/api/v1/knowledge/scholar-profile-papers', params={'scholarId': ID, 'limit': 2})
        self.assertEqual(papers.status_code, 200, papers.text)
        self.assertEqual(papers.json()['data']['items'][0]['id'], PAPER['paper_id'])
        self.assertEqual(papers.json()['data']['items'][0]['imageId'], PAPER['image_id'])

    async def test_query_pagination_and_invalid_input(self):
        response = await self.client.get('/api/v1/knowledge/scholar-profiles/search', params={'q': '何恺明', 'limit': 1, 'offset': 2})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['offset'], 2)
        for params in ({}, {'q': ' '}, {'q': 'x', 'limit': -1}, {'q': 'x', 'offset': -1}):
            bad = await self.client.get('/api/v1/knowledge/scholar-profiles/search', params=params)
            self.assertEqual(bad.status_code, 422)
            self.assertEqual(bad.json()['code'], 'INVALID_ARGUMENT')

    async def test_browse_preserves_enriched_profile_and_validates_pagination(self):
        response = await self.client.get('/api/v1/knowledge/scholar-profiles', params={'limit': 1, 'offset': 1})
        self.assertEqual(response.status_code, 200, response.text)
        page = response.json()['data']
        self.assertEqual((page['total'], page['has_more']), (3, True))
        row = page['items'][0]
        self.assertEqual(row['topics'], ['Machine learning'])
        self.assertEqual(row['employment'][0]['start_date'], '2024-06')
        self.assertEqual(row['metrics']['source_work_count'], 17)
        self.assertEqual(row['metrics']['i10_index'], 0)
        self.assertEqual(row['avatar_path'], '/api/v1/knowledge/scholar-avatar?path=%2Fimages%2Fscholars_example%2Favatar.jpg')
        invalid = await self.client.get('/api/v1/knowledge/scholar-profiles', params={'limit': 101})
        self.assertEqual(invalid.status_code, 422)
