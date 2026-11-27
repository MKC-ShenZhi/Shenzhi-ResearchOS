"""知识库工具输出须在上下文截断前保持完整 JSON。"""
import json
import unittest
from types import SimpleNamespace

from agent_app.capabilities.knowledge import knowledge_tools
from agent_app.execution.types import ToolCall


class FakeKnowledgeService:
    def __init__(self, count=20, authors=()):
        self.requests = []
        self.results = [
            {'id': f'paper:{i}', 'title': f'论文 {i} ' + 'Long title ' * 15,
             'abstract': '长摘要。' * 1000, 'authors': list(authors), 'year': 2026,
             'venue': 'AAAI', 'keywords': [f'keyword-{n}' for n in range(10)]}
            for i in range(count)
        ]

    async def search(self, request):
        self.requests.append(request)
        return {'results': self.results}


class PaperSearchOutputTests(unittest.IsolatedAsyncioTestCase):
    async def search(self, service, limit):
        search = next(item for item in knowledge_tools(service) if item.spec.name == 'paper_search')
        call = ToolCall('search-1', 'paper_search', {'query': 'graph learning', 'limit': limit})
        output = await search.execute(call, search.spec.params_model.model_validate(call.arguments))
        return output

    async def test_long_results_fit_limit_and_sparse_uses_actual_top_k(self):
        service = FakeKnowledgeService()
        output = await self.search(service, 50)
        body = json.loads(output)
        self.assertLessEqual(len(output), 7500)
        self.assertEqual(service.requests[0]['topK'], 20)
        self.assertFalse(body['sparse'])
        self.assertTrue(body['results'])
        self.assertGreater(body.get('omitted', 0), 0)
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
                self.assertEqual(service.requests[0]['topK'], expected_top_k)

    async def test_search_and_detail_return_evidence_without_reference_selection(self):
        service = FakeKnowledgeService(count=20, authors=['Ada'])
        tools = {item.spec.name: item for item in knowledge_tools(service)}
        search = tools['paper_search']
        output = await search.execute(ToolCall('s1', 'paper_search', {}),
                                      search.spec.params_model(query='q', limit=20))
        retained = json.loads(output)['results']
        self.assertTrue(retained)
        self.assertNotIn('references', json.loads(output))

        async def get_paper(_paper_id):
            return SimpleNamespace(**service.results[0], doi='10.1/test',
                                   pdf_url='https://example.test/paper.pdf')

        service.get_paper = get_paper
        detail = tools['paper_detail']
        detailed = await detail.execute(ToolCall('d1', 'paper_detail', {}),
                                        detail.spec.params_model(paper_id='paper:0'))
        payload = json.loads(detailed)
        self.assertEqual(payload['paper_id'], retained[0]['paper_id'])
        self.assertEqual(payload['doi'], '10.1/test')
        self.assertEqual(payload['authors'], ['Ada'])
        self.assertNotIn('references', payload)
