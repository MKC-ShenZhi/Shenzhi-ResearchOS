import unittest
from unittest.mock import patch

import httpx

from app.api import paper_resource as paper_resource_api
from app.core.identity import require_bff
from app.main import app
from app.schemas.knowledge import PaperDetail, Provenance
from app.services.paper_resource import PaperResourceService


PAPER_ID = 'paper:test:123'


class StubKnowledgeService:
    def __init__(self, pdf_url: str | None):
        self.pdf_url = pdf_url

    async def get_paper(self, paper_id: str) -> PaperDetail:
        return PaperDetail(
            id=paper_id,
            title='Paper resource test',
            pdf_url=self.pdf_url,
            provenance=Provenance(),
        )


class PaperResourceApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.dependency_overrides[require_bff] = lambda: None
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://127.0.0.1',
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_streams_trusted_pdf_by_paper_id_with_range(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-7/1024',
                    'content-length': '8',
                    'accept-ranges': 'bytes',
                },
                content=b'%PDF-1.7',
            )

        with (
            patch.object(
                paper_resource_api,
                'knowledge_service',
                StubKnowledgeService('https://papers.example/paper.pdf'),
            ),
            patch.object(
                paper_resource_api,
                'paper_resource_service',
                PaperResourceService(transport=httpx.MockTransport(handler)),
            ),
        ):
            response = await self.client.get(
                '/api/v1/paper-resource/pdf',
                params={'paperId': PAPER_ID},
                headers={'Range': 'bytes=0-7'},
            )

        self.assertEqual(response.status_code, 206, response.text)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertEqual(response.headers['content-range'], 'bytes 0-7/1024')
        self.assertEqual(response.headers['content-disposition'], 'inline')
        self.assertEqual(response.content, b'%PDF-1.7')
        self.assertEqual(requests[0].headers['range'], 'bytes=0-7')

    async def test_does_not_accept_an_arbitrary_proxy_url(self):
        with patch.object(
            paper_resource_api,
            'knowledge_service',
            StubKnowledgeService('https://papers.example/paper.pdf'),
        ):
            response = await self.client.get(
                '/api/v1/paper-resource/pdf',
                params={
                    'paperId': PAPER_ID,
                    'url': 'https://attacker.example/file.pdf',
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'INVALID_ARGUMENT')

    async def test_missing_pdf_is_a_non_retryable_not_found(self):
        with patch.object(
            paper_resource_api,
            'knowledge_service',
            StubKnowledgeService(None),
        ):
            response = await self.client.get(
                '/api/v1/paper-resource/pdf',
                params={'paperId': PAPER_ID},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')
        self.assertFalse(response.json()['retryable'])


if __name__ == '__main__':
    unittest.main()
