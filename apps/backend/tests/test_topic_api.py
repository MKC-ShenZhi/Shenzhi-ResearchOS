import unittest
from unittest.mock import patch

import httpx

from app.core.identity import require_bff
from app.main import app
from app.schemas.topic import KnowledgeTopic
from app.services.topics.registry import TopicRegistry


class TopicApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def allow_bff():
            return None

        app.dependency_overrides[require_bff] = allow_bff
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test',
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.pop(require_bff, None)

    async def test_topic_list_returns_enabled_topics_and_stable_categories(self):
        response = await self.client.get('/api/v1/knowledge/topics')

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()['data']
        self.assertEqual(data['total'], 293)
        self.assertEqual(
            set(data['categories']),
            {'大语言模型', '多模态', '机器学习', '计算机视觉', '生成式AI', '语音/音频处理', '智能体', '自然语言处理'},
        )
        self.assertEqual(data['items'][0]['id'], 'reinforcement-learning')
        self.assertEqual(data['items'][0]['subjectQuery'], 'reinforcement learning')
        self.assertNotIn('descriptionEh', data['items'][0])

    async def test_topic_detail_returns_metadata_by_stable_id(self):
        response = await self.client.get(
            '/api/v1/knowledge/topics/large-language-models'
        )

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()['data']
        self.assertEqual(data['nameZh'], '大语言模型')
        self.assertEqual(data['subjectQuery'], 'large language models')

    async def test_new_catalog_topic_detail_returns_metadata_by_stable_id(self):
        response = await self.client.get('/api/v1/knowledge/topics/contrastive-learning')

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()['data']
        self.assertEqual(data['category'], '机器学习')
        self.assertEqual(data['subjectQuery'], 'contrastive learning')
        self.assertEqual(data['author']['id'], 'shenzhi')

    async def test_missing_topic_returns_unified_not_found_error(self):
        response = await self.client.get('/api/v1/knowledge/topics/missing-topic')

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')
        self.assertTrue(response.json()['requestId'])

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

