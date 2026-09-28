import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from app.core.config import paper_resource_config
from app.integrations.paper_resource.base import PDFProvider, ProviderValidation
from app.integrations.paper_resource.http import HTTPProvider
from app.integrations.paper_resource.openreview import OpenReviewProvider, _note_id
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

    async def test_openreview_forum_url_is_selected_and_uses_api_pdf(self):
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

        with patch.dict('os.environ', {
            'OPENREVIEW_USERNAME': '',
            'OPENREVIEW_PASSWORD': '',
        }):
            service = PaperResourceService(transport=httpx.MockTransport(handler))

        result = await service.resolve_paper_resource(
            'https://openreview.net/forum?id=note-123&referrer=%5BHomepage%5D'
        )

        self.assertEqual(result.status, 'available')
        self.assertEqual(result.provider, 'openreview')
        self.assertEqual(result.url, 'https://api2.openreview.net/pdf?id=note-123')
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


class OpenReviewProviderTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def provider(
        handler,
        *,
        username: str = 'researcher@example.com',
        password: str = 'secret',
        max_size_bytes: int = 10 * 1024 * 1024,
        api_base_url: str = 'https://api2.openreview.net',
        client_factory=None,
    ) -> OpenReviewProvider:
        client_factory = client_factory or Mock(
            return_value=SimpleNamespace(token='token-1')
        )
        return OpenReviewProvider(
            HTTPProvider(
                timeout=30,
                max_size_bytes=max_size_bytes,
                transport=httpx.MockTransport(handler),
            ),
            api_base_url=api_base_url,
            username=username,
            password=password,
            client_factory=client_factory,
        )

    def test_extracts_note_id_from_supported_openreview_urls(self):
        self.assertEqual(
            _note_id('https://openreview.net/forum?id=forum-note&referrer=home'),
            'forum-note',
        )
        self.assertEqual(
            _note_id('https://api2.openreview.net/pdf?id=pdf-note'),
            'pdf-note',
        )
        self.assertEqual(
            _note_id('https://openreview.net/pdf/path-note'),
            'path-note',
        )
        self.assertIsNone(_note_id('https://openreview.net/group?id=not-a-note'))

    async def test_v2_pdf_uses_sdk_token_and_preserves_range(self):
        requests = []
        client_factory = Mock(return_value=SimpleNamespace(token='token-1'))

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 10-19/100',
                },
                content=b'%PDF-authenticated',
            )

        fetch = await self.provider(
            handler,
            client_factory=client_factory,
        ).open(
            'https://openreview.net/forum?id=note-123',
            range_header='bytes=10-19',
        )

        self.assertTrue(fetch.validation.available)
        client_factory.assert_called_once_with(
            baseurl='https://api2.openreview.net',
            username='researcher@example.com',
            password='secret',
        )
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), 'https://api2.openreview.net/pdf?id=note-123')
        self.assertEqual(requests[0].headers['authorization'], 'Bearer token-1')
        self.assertEqual(requests[0].headers['range'], 'bytes=10-19')
        self.assertEqual(requests[0].headers['accept'], 'application/pdf')
        self.assertEqual(requests[0].headers['accept-encoding'], 'identity')
        await fetch.close()

    async def test_token_is_reused_across_multiple_range_requests(self):
        pdf_requests = []
        client_factory = Mock(return_value=SimpleNamespace(token='cached-token'))

        def handler(request: httpx.Request) -> httpx.Response:
            pdf_requests.append(request)
            return httpx.Response(206, headers={'content-type': 'application/pdf'})

        provider = self.provider(handler, client_factory=client_factory)
        first = await provider.open(
            'https://openreview.net/pdf?id=note-123',
            range_header='bytes=0-9',
        )
        second = await provider.open(
            'https://openreview.net/pdf?id=note-123',
            range_header='bytes=10-19',
        )

        self.assertEqual(client_factory.call_count, 1)
        self.assertEqual(
            [request.headers['range'] for request in pdf_requests],
            ['bytes=0-9', 'bytes=10-19'],
        )
        await first.close()
        await second.close()

    async def test_v2_404_falls_back_to_v1_with_same_token_and_range(self):
        requests = []
        attempts = []
        client_factory = Mock(return_value=SimpleNamespace(token='shared-token'))

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == 'api2.openreview.net':
                return httpx.Response(404)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-7/1024',
                },
                content=b'%PDF-1.7',
            )

        with patch(
            'app.integrations.paper_resource.openreview.log_event',
            side_effect=lambda _logger, _level, event, fields: (
                attempts.append((event, fields))
            ),
        ):
            fetch = await self.provider(
                handler,
                client_factory=client_factory,
            ).open(
                'https://openreview.net/forum?id=GcM7qfl5zY',
                range_header='bytes=0-7',
            )

        self.assertTrue(fetch.validation.available)
        self.assertEqual(fetch.validation.status_code, 206)
        self.assertEqual(
            b''.join([chunk async for chunk in fetch.iter_bytes()]),
            b'%PDF-1.7',
        )
        self.assertEqual(client_factory.call_count, 1)
        self.assertEqual(
            [str(request.url) for request in requests],
            [
                'https://api2.openreview.net/pdf?id=GcM7qfl5zY',
                'https://api.openreview.net/pdf?id=GcM7qfl5zY',
            ],
        )
        self.assertTrue(all(
            request.headers['authorization'] == 'Bearer shared-token'
            for request in requests
        ))
        self.assertTrue(all(
            request.headers['range'] == 'bytes=0-7'
            for request in requests
        ))
        self.assertEqual(
            [
                (event, fields['api_version'], fields['status_code'])
                for event, fields in attempts
            ],
            [
                ('paper_resource.openreview_attempt', 'v2', 404),
                ('paper_resource.openreview_attempt', 'v1', 206),
            ],
        )
        self.assertTrue(all(
            'token' not in fields and 'authorization' not in fields
            for _, fields in attempts
        ))
        await fetch.close()

    async def test_v2_and_v1_404_preserve_not_found_without_web_fallback(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(404)

        fetch = await self.provider(handler).open(
            'https://openreview.net/forum?id=missing-note'
        )

        self.assertFalse(fetch.validation.available)
        self.assertEqual(fetch.validation.status_code, 404)
        self.assertEqual(
            [request.url.host for request in requests],
            [
                'api2.openreview.net',
                'api.openreview.net',
            ],
        )
        await fetch.close()

    async def test_auth_failure_refreshes_sdk_client_and_retries_once(self):
        pdf_tokens = []
        ranges = []
        client_factory = Mock(side_effect=[
            SimpleNamespace(token='token-1'),
            SimpleNamespace(token='token-2'),
        ])

        def handler(request: httpx.Request) -> httpx.Response:
            pdf_tokens.append(request.headers.get('authorization'))
            ranges.append(request.headers.get('range'))
            if len(pdf_tokens) == 1:
                return httpx.Response(403)
            return httpx.Response(206, headers={'content-type': 'application/pdf'})

        fetch = await self.provider(
            handler,
            client_factory=client_factory,
        ).open(
            'https://openreview.net/forum?id=note-123',
            range_header='bytes=20-29',
        )

        self.assertTrue(fetch.validation.available)
        self.assertEqual(client_factory.call_count, 2)
        self.assertEqual(pdf_tokens, ['Bearer token-1', 'Bearer token-2'])
        self.assertEqual(ranges, ['bytes=20-29', 'bytes=20-29'])
        await fetch.close()

    async def test_v1_auth_failure_refreshes_once_after_v2_404(self):
        requests = []
        client_factory = Mock(side_effect=[
            SimpleNamespace(token='token-1'),
            SimpleNamespace(token='token-2'),
        ])

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == 'api2.openreview.net':
                return httpx.Response(404)
            if request.headers['authorization'] == 'Bearer token-1':
                return httpx.Response(401)
            return httpx.Response(200, headers={'content-type': 'application/pdf'})

        fetch = await self.provider(
            handler,
            client_factory=client_factory,
        ).open(
            'https://openreview.net/pdf?id=note-123'
        )

        self.assertTrue(fetch.validation.available)
        self.assertEqual(client_factory.call_count, 2)
        self.assertEqual(
            [
                (request.url.host, request.headers['authorization'])
                for request in requests
            ],
            [
                ('api2.openreview.net', 'Bearer token-1'),
                ('api.openreview.net', 'Bearer token-1'),
                ('api.openreview.net', 'Bearer token-2'),
            ],
        )
        await fetch.close()

    async def test_sdk_login_failure_does_not_use_web_pdf_fallback(self):
        requests = []
        client_factory = Mock(side_effect=RuntimeError('login failed'))

        fetch = await self.provider(
            lambda request: requests.append(request),
            client_factory=client_factory,
        ).open('https://openreview.net/forum?id=note-123')

        self.assertFalse(fetch.validation.available)
        self.assertEqual(fetch.validation.reason, 'resource_unavailable')
        self.assertEqual(requests, [])
        self.assertEqual(
            fetch.validation.url,
            'https://api2.openreview.net/pdf?id=note-123',
        )
        await fetch.close()

    async def test_missing_credentials_uses_openreview_apis_without_auth(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == 'api2.openreview.net':
                return httpx.Response(404)
            return httpx.Response(200, headers={'content-type': 'application/pdf'})

        fetch = await self.provider(handler, username='', password='').open(
            'https://api2.openreview.net/pdf?id=note-123'
        )

        self.assertTrue(fetch.validation.available)
        self.assertEqual(
            [request.url.host for request in requests],
            ['api2.openreview.net', 'api.openreview.net'],
        )
        self.assertTrue(all(
            'authorization' not in request.headers
            for request in requests
        ))
        await fetch.close()

    async def test_concurrent_requests_share_one_sdk_client(self):
        client_factory = Mock(return_value=SimpleNamespace(token='shared-token'))
        provider = self.provider(
            lambda request: httpx.Response(
                206,
                headers={'content-type': 'application/pdf'},
            ),
            client_factory=client_factory,
        )
        first, second = await asyncio.gather(
            provider.open('https://openreview.net/pdf?id=note-123'),
            provider.open(
                'https://openreview.net/pdf?id=note-123',
                range_header='bytes=10-19',
            ),
        )

        self.assertEqual(client_factory.call_count, 1)
        self.assertTrue(first.validation.available)
        self.assertTrue(second.validation.available)
        await first.close()
        await second.close()

    async def test_authenticated_range_failure_is_not_replaced_by_fallback(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(416, headers={'content-range': 'bytes */100'})

        fetch = await self.provider(handler).open(
            'https://openreview.net/forum?id=note-123',
            range_header='bytes=200-300',
        )

        self.assertFalse(fetch.validation.available)
        self.assertEqual(fetch.validation.status_code, 416)
        self.assertEqual(len(requests), 1)
        await fetch.close()

    async def test_authenticated_size_failure_is_not_replaced_by_fallback(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                206,
                headers={
                    'content-type': 'application/pdf',
                    'content-range': 'bytes 0-0/11',
                },
            )

        fetch = await self.provider(handler, max_size_bytes=10).open(
            'https://openreview.net/forum?id=note-123',
            range_header='bytes=0-0',
        )

        self.assertEqual(fetch.validation.reason, 'pdf_too_large')
        self.assertEqual(len(requests), 1)
        await fetch.close()

    async def test_cross_origin_redirect_strips_credentials(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == 'api2.openreview.net':
                return httpx.Response(
                    302,
                    headers={
                        'location': 'https://cdn.openreview.net/paper.pdf',
                        'set-cookie': (
                            'upstream=private; Domain=.openreview.net; Path=/'
                        ),
                    },
                )
            return httpx.Response(206, headers={'content-type': 'application/pdf'})

        provider = HTTPProvider(
            timeout=30,
            max_size_bytes=10 * 1024 * 1024,
            transport=httpx.MockTransport(handler),
        )
        fetch = await provider.open_with_headers(
            'https://api2.openreview.net/pdf?id=note-123',
            range_header='bytes=0-9',
            extra_headers={
                'Authorization': 'Bearer private-token',
                'Cookie': 'session=private',
            },
        )

        self.assertTrue(fetch.validation.available)
        self.assertEqual(requests[0].headers['authorization'], 'Bearer private-token')
        self.assertEqual(requests[0].headers['cookie'], 'session=private')
        self.assertNotIn('authorization', requests[1].headers)
        self.assertNotIn('cookie', requests[1].headers)
        self.assertEqual(requests[1].headers['range'], 'bytes=0-9')
        self.assertEqual(requests[1].headers['accept'], 'application/pdf')
        self.assertEqual(requests[1].headers['accept-encoding'], 'identity')
        await fetch.close()


class PaperResourceConfigTests(unittest.IsolatedAsyncioTestCase):
    def test_configuration_reads_timeout_and_max_megabytes(self):
        with patch.dict('os.environ', {
            'PAPER_RESOURCE_TIMEOUT': '12.5',
            'PAPER_MAX_SIZE_MB': '2',
            'OPENREVIEW_API_BASE_URL': 'https://api.openreview.net/',
            'OPENREVIEW_USERNAME': ' researcher@example.com ',
            'OPENREVIEW_PASSWORD': 'secret',
        }):
            config = paper_resource_config()

        self.assertEqual(config.timeout_seconds, 12.5)
        self.assertEqual(config.max_size_bytes, 2 * 1024 * 1024)
        self.assertEqual(
            config.openreview_api_base_url,
            'https://api.openreview.net',
        )
        self.assertEqual(config.openreview_username, 'researcher@example.com')
        self.assertEqual(config.openreview_password, 'secret')

    def test_invalid_configuration_falls_back_to_safe_defaults(self):
        with patch.dict('os.environ', {
            'PAPER_RESOURCE_TIMEOUT': 'invalid',
            'PAPER_MAX_SIZE_MB': '0',
            'OPENREVIEW_API_BASE_URL': '',
            'OPENREVIEW_USERNAME': '',
            'OPENREVIEW_PASSWORD': '',
        }):
            config = paper_resource_config()

        self.assertEqual(config.timeout_seconds, 30.0)
        self.assertEqual(config.max_size_bytes, 150 * 1024 * 1024)
        self.assertEqual(
            config.openreview_api_base_url,
            'https://api2.openreview.net',
        )
        self.assertEqual(config.openreview_username, '')
        self.assertEqual(config.openreview_password, '')

    def test_openreview_api_base_url_normalizes_trusted_https_origins(self):
        for configured, expected in (
            ('https://api2.openreview.net/', 'https://api2.openreview.net'),
            ('https://api.openreview.net', 'https://api.openreview.net'),
            ('https://reviews.openreview.net:443/', 'https://reviews.openreview.net'),
        ):
            with self.subTest(configured=configured):
                with patch.dict('os.environ', {
                    'OPENREVIEW_API_BASE_URL': configured,
                }):
                    config = paper_resource_config()
                self.assertEqual(config.openreview_api_base_url, expected)

    def test_untrusted_openreview_api_base_urls_fall_back_to_default(self):
        untrusted_urls = (
            'http://api2.openreview.net',
            'https://evil.com',
            'https://openreview.net.evil.com',
            'https://evilopenreview.net',
            'https://user:pass@api2.openreview.net',
            'https://api2.openreview.net/login',
            'https://api2.openreview.net?x=1',
            'https://127.0.0.1',
            'https://api2.openreview.net:8443',
        )
        for configured in untrusted_urls:
            with self.subTest(configured=configured):
                with patch.dict('os.environ', {
                    'OPENREVIEW_API_BASE_URL': configured,
                }):
                    config = paper_resource_config()
                self.assertEqual(
                    config.openreview_api_base_url,
                    'https://api2.openreview.net',
                )

    async def test_provider_never_sends_credentials_to_untrusted_api_base(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == '/login':
                return httpx.Response(401)
            return httpx.Response(200, headers={'content-type': 'application/pdf'})

        fetch = await OpenReviewProviderTests.provider(
            handler,
            api_base_url='https://evil.com',
        ).open('https://openreview.net/pdf?id=note-123')

        self.assertEqual(requests[0].url.host, 'api2.openreview.net')
        self.assertNotIn('evil.com', [request.url.host for request in requests])
        await fetch.close()


if __name__ == '__main__':
    unittest.main()
