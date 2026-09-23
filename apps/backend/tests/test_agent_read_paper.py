import json
import unittest
from types import SimpleNamespace

import httpx

from app.services.agent.read_paper import read_paper_tool
from app.services.agent.types import ToolCall


class StubKnowledgeService:
    def __init__(self):
        self.paper_ids: list[str] = []

    async def get_paper(self, paper_id: str):
        self.paper_ids.append(paper_id)
        return SimpleNamespace(pdf_url='https://1.1.1.1/fulltext')


class ReadPaperIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_opaque_paper_id_is_forwarded_to_knowledge_without_rewriting(self):
        knowledge = StubKnowledgeService()
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200,
            headers={'content-type': 'text/html; charset=utf-8'},
            content=b'<main>Fallback page text</main>',
            request=request,
        ))
        tool = read_paper_tool(knowledge=knowledge, transport=transport)
        paper_id = 'paper:opaque/value?part=1%2Fsection'
        args = tool.spec.params_model.model_validate({'paper_id': paper_id})

        output = await tool.execute(ToolCall('call-1', 'read_paper', {'paper_id': paper_id}), args)

        self.assertEqual(knowledge.paper_ids, [paper_id])
        self.assertFalse(json.loads(output)['pdf'])


if __name__ == '__main__':
    unittest.main()
