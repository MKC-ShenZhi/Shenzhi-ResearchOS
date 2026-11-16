import asyncio
import copy
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.core.identity import require_bff
from app.integrations.knowledge.adapter import KnowledgeAdapter
from app.integrations.knowledge.client import KnowledgeBaseClient
from app.main import app
from app.services.library.topic_follows import TopicFollowService
from app.services.topics.openalex import OpenAlexTopicRegistry
from app.schemas.topic import KnowledgeTopic
from app.services.topics.catalog import CATALOG_PATH, load_topic_catalog
from app.services.topics.registry import TopicRegistry


TOPIC_ID = 'openalex:topic:T10028'
TOPIC_SEGMENT = 'openalex%3Atopic%3AT10028'
CATEGORY_ID = 'openalex:subfield:1702'
TOPIC = {
    'id': TOPIC_ID, 'level': 'topic', 'parentId': CATEGORY_ID,
    'nameEn': 'Natural Language Processing Models and Representations',
    'nameZh': '自然语言处理模型与表示', 'descriptionZh': '主题介绍',
    'paperCount': 12379, 'enabled': True, 'imagePath': '/images/topics/default.png',
}
TREE = [{
    'id': 'openalex:domain:3', 'level': 'domain', 'enabled': True,
    'children': [{
        'id': 'openalex:field:17', 'level': 'field', 'enabled': True,
        'children': [
            {
                'id': CATEGORY_ID, 'level': 'subfield', 'nameEn': 'Artificial Intelligence',
                'enabled': True, 'children': [
                    {**TOPIC, 'children': []},
                    {**TOPIC, 'id': 'openalex:topic:T10181', 'enabled': False, 'children': []},
                ],
            },
            {
                'id': 'openalex:subfield:1707', 'level': 'subfield', 'nameZh': '计算机视觉',
                'enabled': True, 'children': [
                    {**TOPIC, 'id': 'openalex:topic:T11689', 'parentId': 'openalex:subfield:1707',
                     'nameZh': None, 'descriptionZh': None, 'children': []},
                ],
            },
        ],
    }],
}]


class TopicApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        load_topic_catalog.cache_clear()
        self.addCleanup(load_topic_catalog.cache_clear)
        async def allow_bff():
            return None

        app.dependency_overrides[require_bff] = allow_bff
        self.tree = copy.deepcopy(TREE)
        self.requests = []
        self.failure = None
        adapter = KnowledgeAdapter(KnowledgeBaseClient(
            base_url='https://knowledge.test',
            transport=httpx.MockTransport(self.upstream),
        ))
        self.registry = OpenAlexTopicRegistry(adapter)
        self.enterContext(patch('app.api.knowledge.openalex_topics', self.registry))
        self.enterContext(patch('app.api.interactions.follows', TopicFollowService(self.registry)))
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test',
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.pop(require_bff, None)

    async def upstream(self, request):
        self.requests.append(request.url)
        if self.failure == 'timeout':
            raise httpx.ReadTimeout('fixture timeout', request=request)
        if self.failure:
            return httpx.Response(self.failure, json={})
        if request.url.path == '/api/v1/topics/tree':
            return httpx.Response(200, json={'tree': self.tree})
        if request.url.path == f'/api/v1/topics/{TOPIC_ID}':
            return httpx.Response(200, json=TOPIC)
        if request.url.path == f'/api/v1/topics/{TOPIC_ID}/papers':
            offset = int(request.url.params['offset'])
            limit = int(request.url.params['limit'])
            return httpx.Response(200, json={
                'items': [] if offset >= 12379 else [{
                    'id': 16349, 'paper_id': 'paper:stable:123', 'title': 'Related Paper',
                    'authors': ['A. Researcher'], 'conference': 'NAACL',
                    'topics': [{'id': TOPIC_ID, 'nameEn': TOPIC['nameEn']}],
                }],
                'total': 12379, 'limit': limit, 'offset': offset,
            })
        return httpx.Response(404, json={})

    async def test_directory_uses_default_tree_filters_leaves_and_shares_cache(self):
        path = '/api/v1/knowledge/topics'
        responses = await asyncio.gather(self.client.get(path), self.client.get(path))
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()['data']
            self.assertEqual(data['total'], 2)
            self.assertEqual(data['categories'], [
                {'id': CATEGORY_ID, 'name': 'Artificial Intelligence', 'total': 1},
                {'id': 'openalex:subfield:1707', 'name': '计算机视觉', 'total': 1},
            ])
            self.assertEqual(sum(category['total'] for category in data['categories']), data['total'])
            self.assertEqual({item['id'] for item in data['items']}, {TOPIC_ID, 'openalex:topic:T11689'})
            self.assertEqual(data['items'][1]['nameZh'], TOPIC['nameEn'])
            self.assertEqual(data['items'][1]['descriptionZh'], '')
        self.assertEqual([url.raw_path for url in self.requests], [b'/api/v1/topics/tree'])

    async def test_encoded_detail_and_papers_use_leaf_id_and_stable_paper_id(self):
        path = f'/api/v1/knowledge/topics/{TOPIC_SEGMENT}'
        detail = await self.client.get(path)
        self.assertEqual(detail.status_code, 200, detail.text)
        topic = detail.json()['data']
        self.assertEqual(topic['id'], TOPIC_ID)
        self.assertEqual(topic['category'], CATEGORY_ID)
        self.assertEqual(topic['nameZh'], TOPIC['nameZh'])
        self.assertEqual(topic['descriptionZh'], TOPIC['descriptionZh'])
        self.assertEqual(topic['paperCount'], TOPIC['paperCount'])
        self.assertIsNone(topic['author'])
        self.assertIsNone(topic['imagePath'])
        self.assertIsNone(topic['descriptionDetail'])

        papers = await self.client.get(f'{path}/papers?offset=1001&limit=2')
        self.assertEqual(papers.status_code, 200, papers.text)
        page = papers.json()['data']
        self.assertEqual((page['offset'], page['limit'], page['total']), (1001, 2, 12379))
        self.assertEqual(page['results'][0]['id'], 'paper:stable:123')
        self.assertEqual(page['results'][0]['venue'], 'NAACL')
        self.assertEqual(page['results'][0]['subjects'], [])
        self.assertEqual(page['results'][0]['topics'], [
            {'id': TOPIC_ID, 'nameZh': None, 'nameEn': TOPIC['nameEn']},
        ])
        self.assertEqual([url.raw_path.decode() for url in self.requests], [
            '/api/v1/topics/tree', f'/api/v1/topics/{TOPIC_SEGMENT}',
            f'/api/v1/topics/{TOPIC_SEGMENT}/papers?limit=2&offset=1001',
        ])
        self.assertEqual((await self.client.get(f'{path}/papers?offset=12379')).json()['data']['results'], [])

    async def test_legacy_disabled_parent_and_static_paths_do_not_resolve(self):
        for topic_id in ('deep-learning', 'openalex%3Atopic%3AT10181', 'openalex%3Asubfield%3A1702', 'tree'):
            for suffix in ('', '/papers'):
                response = await self.client.get(f'/api/v1/knowledge/topics/{topic_id}{suffix}')
                self.assertEqual(response.status_code, 404, response.text)
                self.assertEqual(response.json()['code'], 'NOT_FOUND')
        self.assertEqual([url.path for url in self.requests], ['/api/v1/topics/tree'])

    async def test_failed_refresh_returns_retryable_error_and_can_recover(self):
        path = '/api/v1/knowledge/topics'
        self.failure = 'timeout'
        failed = await self.client.get(path)
        self.assertEqual(failed.status_code, 504, failed.text)
        self.assertTrue(failed.json()['retryable'])
        self.failure = None
        self.assertEqual((await self.client.get(path)).json()['data']['total'], 2)

        self.registry._expires_at = 0
        self.tree[0]['children'][0]['children'].pop()
        updated = (await self.client.get(path)).json()['data']
        self.assertEqual(updated['total'], 1)
        self.assertEqual(len(updated['categories']), 1)

    async def test_duplicate_ids_reject_invalid_catalog(self):
        children = self.tree[0]['children'][0]['children'][0]['children']
        children.append(children[0])
        response = await self.client.get('/api/v1/knowledge/topics')
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(response.json()['code'], 'CONTRACT_VIOLATION')

    async def test_paper_errors_and_invalid_pagination(self):
        await self.registry.list_topics()
        path = f'/api/v1/knowledge/topics/{TOPIC_SEGMENT}/papers'
        for failure, status in ((404, 404), ('timeout', 504), (503, 503)):
            with self.subTest(failure=failure):
                self.failure = failure
                self.assertEqual((await self.client.get(path)).status_code, status)
        for query in ('offset=-1', 'limit=0', 'limit=101'):
            self.assertEqual((await self.client.get(f'{path}?{query}')).status_code, 422)

    async def test_follow_rejects_legacy_and_disabled_ids_before_database_write(self):
        headers = {'x-shenzhi-bff-secret': 'test-secret', 'x-shenzhi-user-id': 'user-a'}
        with patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'}):
            for topic_id in ('deep-learning', 'openalex%3Atopic%3AT10181'):
                response = await self.client.put(f'/api/v1/topic-follows/{topic_id}', headers=headers)
                self.assertEqual(response.status_code, 404, response.text)
            self.assertEqual((await self.client.put(
                f'/api/v1/topic-follows/{TOPIC_SEGMENT}',
                headers={'x-shenzhi-bff-secret': 'test-secret'},
            )).status_code, 401)

    async def test_topic_routes_return_safe_500_on_unexpected_registry_error(self):
        for path, method in [
            ('/api/v1/knowledge/topics', 'list_topics'),
            (f'/api/v1/knowledge/topics/{TOPIC_SEGMENT}', 'get_topic'),
            (f'/api/v1/knowledge/topics/{TOPIC_SEGMENT}/papers', 'papers'),
        ]:
            with self.subTest(path=path), patch.object(
                self.registry, method, side_effect=RuntimeError('private internal detail'),
            ):
                response = await self.client.get(path, headers={'x-request-id': 'topic-regression'})
                self.assertEqual(response.status_code, 500, response.text)
                self.assertEqual(response.json(), {
                    'code': 'UNKNOWN', 'message': '知识服务请求失败',
                    'retryable': False, 'requestId': 'topic-regression',
                })

    async def test_knowledge_service_unexpected_errors_use_same_500_contract(self):
        cases = [
            ('GET', '/api/v1/knowledge/overview', 'overview', None),
            ('GET', '/api/v1/knowledge/paper?paperId=test', 'get_paper', None),
            ('GET', '/api/v1/knowledge/graph?paperId=test', 'get_graph', None),
            ('GET', '/api/v1/knowledge/subjects/search?subject=llm', 'search_by_subject', None),
            ('POST', '/api/v1/knowledge/search', 'search', {'query': 'llm'}),
        ]
        for verb, path, method, body in cases:
            with self.subTest(path=path), patch(
                f'app.api.knowledge.service.{method}',
                side_effect=RuntimeError('private internal detail'),
            ):
                response = await self.client.request(verb, path, json=body)
                self.assertEqual(response.status_code, 500, response.text)
                self.assertEqual(response.json()['code'], 'UNKNOWN')
                self.assertEqual(response.json()['message'], '知识服务请求失败')
                self.assertFalse(response.json()['retryable'])
                self.assertTrue(response.json()['requestId'])

    async def test_creator_not_found_keeps_404_contract(self):
        response = await self.client.get('/api/v1/knowledge/creators/missing')
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')

    def test_fresh_application_import_does_not_load_catalog(self):
        result = subprocess.run(
            [sys.executable, '-c', textwrap.dedent('''
                from unittest.mock import patch
                from app.services.topics.catalog import TopicCatalogError

                with patch('app.services.topics.registry.load_topic_catalog',
                           side_effect=TopicCatalogError('catalog unavailable')) as load:
                    from app.main import app
                    assert '/api/v1/knowledge/topics' in app.openapi()['paths']
                    load.assert_not_called()
            ''')],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    async def test_legacy_creator_failures_are_logged_and_isolated_from_other_routes(self):
        paths = [
            '/api/v1/knowledge/creators/shenzhi',
            '/api/v1/knowledge/creators/missing',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private-catalog.json'
            for content in [None, b'{', b'[{"id": "invalid"}]', b'\xff']:
                with self.subTest(content=content):
                    load_topic_catalog.cache_clear()
                    if content is not None:
                        path.write_bytes(content)
                    with patch('app.services.topics.catalog.CATALOG_PATH', path):
                        for route in paths:
                            with self.subTest(route=route), self.assertLogs('app.api.knowledge', 'ERROR') as logs:
                                response = await self.client.get(route, headers={'x-request-id': 'catalog-failure'})
                            self.assertEqual(response.status_code, 500, response.text)
                            self.assertEqual(response.json(), {
                                'code': 'UNKNOWN', 'message': '知识服务请求失败',
                                'retryable': False, 'requestId': 'catalog-failure',
                            })
                            self.assertTrue(any(record.exc_info for record in logs.records))

                        health = await self.client.get('/health')
                        self.assertEqual(health.status_code, 200, health.text)
                        with patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'}):
                            overview = await self.client.get('/api/v1/knowledge/personal-overview', headers={
                                'x-shenzhi-bff-secret': 'test-secret',
                                'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
                            })
                        self.assertEqual(overview.status_code, 200, overview.text)
                        self.assertTrue(overview.json()['data']['authRequired'])

    def test_registry_filters_disabled_topics_without_losing_category_order(self):
        topics = (
            KnowledgeTopic(
                id='one', imagePath=None, nameZh='一', nameEn='One', author='shenzhi',
                descriptionZh='一', descriptionEn='One', category='A', subjectQuery='one',
                paperCount=1, enabled=True,
            ),
            KnowledgeTopic(
                id='hidden', imagePath=None, nameZh='隐藏', nameEn='Hidden', author='shenzhi',
                descriptionZh='隐藏', descriptionEn='Hidden', category='B', subjectQuery='hidden',
                paperCount=2, enabled=False,
            ),
            KnowledgeTopic(
                id='two', imagePath=None, nameZh='二', nameEn='Two', author='shenzhi',
                descriptionZh='二', descriptionEn='Two', category='A', subjectQuery='two',
                paperCount=3, enabled=True,
            ),
        )
        result = TopicRegistry(topics).list_topics()

        self.assertEqual([topic.id for topic in result.items], ['one', 'two'])
        self.assertEqual(result.categories, ['A'])


if __name__ == '__main__':
    unittest.main()

