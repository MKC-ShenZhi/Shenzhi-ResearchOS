"""Product topic metadata must not break the strict Agent Knowledge boundary."""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from agent_contracts import KnowledgePaperDetailWire, KnowledgeSearchResponseWire

from app.main import app
from app.schemas.knowledge import KnowledgeSearchResponse, PaperDetail, PaperSearchResult


class AgentKnowledgeContractTests(unittest.IsolatedAsyncioTestCase):
    def paper(self):
        return {
            'id': 'paper-knowledge-editing', 'title': 'Knowledge Editing',
            'topics': [{'id': 'topic-editing', 'nameZh': '知识编辑', 'nameEn': 'Knowledge Editing'}],
            'provenance': {'provider': 'knowledge-base'},
        }

    async def test_search_with_product_topics_returns_agent_wire(self):
        result = KnowledgeSearchResponse(
            results=[PaperSearchResult.model_validate(self.paper())], has_more=True, total=12,
        )
        with patch.dict('os.environ', {'AGENT_SERVICE_TOKEN': 'test-knowledge-token'}), patch(
            'app.api.knowledge.service.search', new=AsyncMock(return_value=result),
        ) as search:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/v1/agent/internal/knowledge/search',
                    headers={'Authorization': 'Bearer test-knowledge-token'},
                    json={'query': 'knowledge editing large language models', 'topK': 10})
        self.assertEqual(response.status_code, 200, response.text)
        wire = KnowledgeSearchResponseWire.model_validate(response.json())
        self.assertEqual(wire.results[0].title, 'Knowledge Editing')
        self.assertTrue(wire.has_more)
        self.assertEqual(wire.total, 12)
        self.assertEqual(search.await_args.args[0].top_k, 10)
        self.assertNotIn('topics', response.json()['results'][0])
        self.assertEqual(len(result.results[0].topics), 1)

    async def test_detail_with_product_topics_returns_agent_wire(self):
        result = PaperDetail.model_validate({**self.paper(), 'doi': '10.1234/example'})
        with patch.dict('os.environ', {'AGENT_SERVICE_TOKEN': 'test-knowledge-token'}), patch(
            'app.api.knowledge.service.get_paper', new=AsyncMock(return_value=result),
        ):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.get('/api/v1/agent/internal/knowledge/papers/paper-knowledge-editing',
                    headers={'Authorization': 'Bearer test-knowledge-token'})
        self.assertEqual(response.status_code, 200, response.text)
        wire = KnowledgePaperDetailWire.model_validate(response.json())
        self.assertEqual(wire.doi, '10.1234/example')
        self.assertNotIn('topics', response.json())
        self.assertEqual(len(result.topics), 1)
