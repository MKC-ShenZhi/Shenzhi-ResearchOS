import unittest
from unittest.mock import patch

import httpx

from app.core.config import paper_resource_config
from app.services.paper_resource.providers.base import PDFProvider, ProviderValidation
from app.services.paper_resource.service import PaperResourceService


class PaperResourceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_provider_probes_only_headers_and_returns_browser_url(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf; charset=binary',
                    'content-range': 'bytes 0-0/2048',
                    'content-length': '1',
                },
                content=b'%',
            )

        result = await PaperResourceService(
            transport=httpx.MockTransport(handler)
        ).resolve_paper_resource('https://papers.example/paper.pdf#page=3')

        self.assertEqual(result.status, 'available')
        self.assertEqual(result.provider, 'http')
        self.assertEqual(result.url, 'https://papers.example/paper.pdf')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, 'GET')
        self.assertEqual(requests[0].headers['range'], 'bytes=0-0')
        self.assertEqual(requests[0].headers['accept-encoding'], 'identity')

    async def test_openreview_forum_url_is_selected_and_normalized_to_pdf(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={
                    'content-type': 'application/pdf',
                    'content-length': '4096',
                },
            )

        result = await PaperResourceService(
            transport=httpx.MockTransport(handler)
        ).resolve_paper_resource(
            'https://openreview.net/forum?id=note-123&referrer=%5BHomepage%5D'
        )

        self.assertEqual(result.status, 'available')
        self.assertEqual(result.provider, 'openreview')
        self.assertEqual(result.url, 'https://openreview.net/pdf?id=note-123')
        self.assertEqual(str(requests[0].url), result.url)

    async def test_explicit_non_pdf_content_type_is_unavailable(self):
        result = await PaperResourceService(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={'content-type': 'text/html'},
                )
            )
        ).resolve_paper_resource('https://papers.example/landing')

        self.assertEqual(result.status, 'unavailable')
        self.assertEqual(result.reason, 'invalid_content_type')

    async def test_missing_content_type_is_allowed_when_source_does_not_expose_it(self):
        result = await PaperResourceService(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, headers={'content-length': '20'})
            )
        ).resolve_paper_resource('https://papers.example/paper.pdf')

        self.assertEqual(result.status, 'available')

    async def test_size_limit_uses_total_from_partial_response(self):
        with patch.dict('os.environ', {'PAPER_MAX_SIZE_MB': '1'}):
            service = PaperResourceService(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        206,
                        headers={
                            'content-type': 'application/pdf',
                            'content-range': 'bytes 0-0/1048577',
                            'content-length': '1',
                        },
                    )
                )
            )

        result = await service.resolve_paper_resource(
            'https://papers.example/large.pdf'
        )

        self.assertEqual(result.status, 'unavailable')
        self.assertEqual(result.reason, 'pdf_too_large')

    async def test_timeout_and_invalid_urls_are_non_throwing(self):
        timeout_service = PaperResourceService(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    httpx.ReadTimeout('timed out', request=request)
                )
            )
        )
        timed_out = await timeout_service.resolve_paper_resource(
            'https://papers.example/paper.pdf'
        )
        invalid = await timeout_service.resolve_paper_resource(
            'http://127.0.0.1/private.pdf'
        )

        self.assertEqual((timed_out.status, timed_out.reason), (
            'unavailable', 'request_timeout'
        ))
        self.assertEqual((invalid.status, invalid.reason), (
            'unavailable', 'invalid_pdf_url'
        ))
        self.assertIsNone(invalid.url)

    async def test_unexpected_provider_failure_cannot_break_paper_detail(self):
        class BrokenProvider(PDFProvider):
            name = 'http'

            def match(self, url: str) -> bool:
                return True

            async def validate(self, url: str) -> ProviderValidation:
                raise RuntimeError('provider bug')

        result = await PaperResourceService(
            providers=[BrokenProvider()]
        ).resolve_paper_resource('https://papers.example/paper.pdf')

        self.assertEqual(result.status, 'unavailable')
        self.assertEqual(result.reason, 'resource_unavailable')

    async def test_open_resource_streams_pdf_and_forwards_single_range(self):
        requests = []
        responses = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            response = httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-7/1024',
                    'content-length': '8',
                    'accept-ranges': 'bytes',
                },
                content=b'%PDF-1.7',
            )
            responses.append(response)
            return response

        fetch = await PaperResourceService(
            transport=httpx.MockTransport(handler)
        ).open_paper_resource(
            'https://papers.example/paper.pdf',
            range_header='bytes=0-7',
        )

        self.assertEqual(fetch.resource.status, 'available')
        self.assertEqual(fetch.status_code, 206)
        self.assertEqual(fetch.headers['content-range'], 'bytes 0-7/1024')
        self.assertEqual(
            b''.join([chunk async for chunk in fetch.iter_bytes()]),
            b'%PDF-1.7',
        )
        self.assertEqual(requests[0].headers['range'], 'bytes=0-7')
        self.assertEqual(requests[0].headers['accept-encoding'], 'identity')
        await fetch.close()
        self.assertTrue(responses[0].is_closed)


class PaperResourceConfigTests(unittest.TestCase):
    def test_configuration_reads_timeout_and_max_megabytes(self):
        with patch.dict('os.environ', {
            'PAPER_RESOURCE_TIMEOUT': '12.5',
            'PAPER_MAX_SIZE_MB': '2',
        }):
            config = paper_resource_config()

        self.assertEqual(config.timeout_seconds, 12.5)
        self.assertEqual(config.max_size_bytes, 2 * 1024 * 1024)

    def test_invalid_configuration_falls_back_to_safe_defaults(self):
        with patch.dict('os.environ', {
            'PAPER_RESOURCE_TIMEOUT': 'invalid',
            'PAPER_MAX_SIZE_MB': '0',
        }):
            config = paper_resource_config()

        self.assertEqual(config.timeout_seconds, 30.0)
        self.assertEqual(config.max_size_bytes, 150 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
