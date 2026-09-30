import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from app.api import paper_resource as paper_resource_api
from app.core.identity import require_bff
from app.main import app
from app.integrations.paper_resource.http import HTTPProvider
from app.integrations.paper_resource.openreview import OpenReviewProvider
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
        diagnostics = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-7/1024',
                    # Some upstreams incorrectly report the full PDF length for
                    # a partial body. The proxy must not repeat that promise.
                    'content-length': '1024',
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
            patch.object(
                paper_resource_api,
                'log_event',
                side_effect=lambda _logger, _level, event, fields: (
                    diagnostics.append((event, fields))
                ),
            ),
            patch.dict('os.environ', {'ENVIRONMENT': 'development'}),
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
        self.assertNotIn('content-length', response.headers)
        self.assertEqual(response.content, b'%PDF-1.7')
        self.assertEqual(requests[0].headers['range'], 'bytes=0-7')
        self.assertEqual(len(diagnostics), 1)
        event, fields = diagnostics[0]
        self.assertEqual(event, 'paper_resource.upstream_response')
        self.assertEqual(fields, {
            'paper_id': PAPER_ID,
            'provider': 'http',
            'incoming_range': 'bytes=0-7',
            'upstream_status': 206,
            'upstream_content_length': '1024',
            'upstream_content_range': 'bytes 0-7/1024',
            'upstream_accept_ranges': 'bytes',
        })

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

    async def test_streams_legacy_openreview_pdf_with_range_from_v1(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == 'api2.openreview.net':
                return httpx.Response(404)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-7/1024',
                    'accept-ranges': 'bytes',
                },
                content=b'%PDF-1.7',
            )

        http_provider = HTTPProvider(
            timeout=30,
            max_size_bytes=10 * 1024 * 1024,
            transport=httpx.MockTransport(handler),
        )
        openreview_provider = OpenReviewProvider(
            http_provider,
            username='researcher@example.com',
            password='secret',
            client_factory=Mock(
                return_value=SimpleNamespace(token='shared-token')
            ),
        )
        with (
            patch.object(
                paper_resource_api,
                'knowledge_service',
                StubKnowledgeService(
                    'https://openreview.net/forum?id=GcM7qfl5zY'
                ),
            ),
            patch.object(
                paper_resource_api,
                'paper_resource_service',
                PaperResourceService(providers=[openreview_provider, http_provider]),
            ),
        ):
            response = await self.client.get(
                '/api/v1/paper-resource/pdf',
                params={'paperId': PAPER_ID},
                headers={'Range': 'bytes=0-7'},
            )

        self.assertEqual(response.status_code, 206, response.text)
        self.assertEqual(response.content, b'%PDF-1.7')
        self.assertEqual(response.headers['content-range'], 'bytes 0-7/1024')
        self.assertEqual(
            [request.url.host for request in requests],
            ['api2.openreview.net', 'api.openreview.net'],
        )
        self.assertTrue(all(
            request.headers['authorization'] == 'Bearer shared-token'
            for request in requests
        ))
        self.assertTrue(all(
            request.headers['range'] == 'bytes=0-7'
            for request in requests
        ))

    async def test_openreview_missing_in_both_apis_is_not_found(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(404)

        http_provider = HTTPProvider(
            timeout=30,
            max_size_bytes=10 * 1024 * 1024,
            transport=httpx.MockTransport(handler),
        )
        openreview_provider = OpenReviewProvider(
            http_provider,
            username='researcher@example.com',
            password='secret',
            client_factory=Mock(
                return_value=SimpleNamespace(token='shared-token')
            ),
        )
        with (
            patch.object(
                paper_resource_api,
                'knowledge_service',
                StubKnowledgeService(
                    'https://openreview.net/forum?id=missing-note'
                ),
            ),
            patch.object(
                paper_resource_api,
                'paper_resource_service',
                PaperResourceService(providers=[openreview_provider, http_provider]),
            ),
        ):
            response = await self.client.get(
                '/api/v1/paper-resource/pdf',
                params={'paperId': PAPER_ID},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')
        self.assertEqual(
            [request.url.host for request in requests],
            ['api2.openreview.net', 'api.openreview.net'],
        )
        self.assertNotIn('openreview.net', [
            request.url.host for request in requests
        ])

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
