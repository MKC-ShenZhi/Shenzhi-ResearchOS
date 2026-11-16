"""知识库工具输出须在上下文截断前保持完整 JSON。"""
import json
import unittest

from app.schemas.knowledge import KnowledgeSearchResponse, PaperSearchResult, Provenance
from app.services.agent.knowledge_tools import knowledge_tools
from app.services.agent.types import ToolCall


class FakeKnowledgeService:
    def __init__(self, count=20, authors=()):
        self.requests = []
        self.results = [PaperSearchResult(
            id=f'paper:{i}', title=f'论文 {i} ' + 'Long title ' * 15,
            abstract='长摘要。' * 1000, authors=list(authors), year=2026, venue='AAAI',
            keywords=[f'keyword-{n}' for n in range(10)], provenance=Provenance(),
        ) for i in range(count)]

    async def search(self, request):
        self.requests.append(request)
        return KnowledgeSearchResponse(results=self.results)


class PaperSearchOutputTests(unittest.IsolatedAsyncioTestCase):
    async def search(self, service, limit):
        search = next(item for item in knowledge_tools(service) if item.spec.name == 'paper_search')
        call = ToolCall('search-1', 'paper_search', {'query': 'graph learning', 'limit': limit})
        return await search.execute(call, search.spec.params_model.model_validate(call.arguments))

    async def test_long_results_fit_limit_and_sparse_uses_actual_top_k(self):
        service = FakeKnowledgeService()
        output = await self.search(service, 50)
        body = json.loads(output)
        self.assertLessEqual(len(output), 7500)
        self.assertEqual(service.requests[0].top_k, 20)
        self.assertFalse(body['sparse'])
        self.assertTrue(body['results'])
        self.assertGreater(body['omitted'], 0)
        self.assertEqual(len(body['results']) + body['omitted'], 20)
        self.assertIn('省略了排名靠后的结果', body['note_omitted'])
        self.assertEqual(body['note'], '检索接口不返回作者；需要作者请对该 paper_id 调用 paper_detail。')
        self.assertEqual(output.count('检索接口不返回作者'), 1)
        for item in body['results']:
            self.assertLessEqual(len(item['abstract']), 301)
            self.assertTrue(item['abstract'].endswith('…'))
            self.assertEqual(len(item['keywords']), 5)
            self.assertNotIn('authors_note', item)
        self.assertEqual([item['paper_id'] for item in body['results']],
                         [f'paper:{i}' for i in range(len(body['results']))])

    async def test_small_complete_result_has_no_omission_or_author_note(self):
        body = json.loads(await self.search(FakeKnowledgeService(count=1, authors=['Ada']), 1))
        self.assertFalse(body['sparse'])
        self.assertNotIn('note', body)
        self.assertNotIn('omitted', body)
        self.assertNotIn('note_omitted', body)

    async def test_sparse_result_compares_to_clamped_request(self):
        for limit, returned, expected_top_k in ((50, 19, 20), (3, 2, 3), (0, 0, 1)):
            with self.subTest(limit=limit):
                service = FakeKnowledgeService(count=returned)
                body = json.loads(await self.search(service, limit))
                self.assertTrue(body['sparse'])
                self.assertEqual(service.requests[0].top_k, expected_top_k)
