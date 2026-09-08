"""HTTP transport boundary for the external Knowledge Base API."""

from __future__ import annotations

import os
import logging
import ipaddress
from time import perf_counter
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Literal, Mapping, cast
from urllib.parse import urljoin, urlparse

import httpx

from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.core.logging import log_event
from app.integrations.knowledge.schemas import (
    UpstreamGraphResponse,
    UpstreamPaperResponse,
    UpstreamSearchResponse,
)


DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_PDF_REDIRECTS = 3
PDF_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfProbe:
    status: Literal['available', 'external_only', 'unavailable']
    retryable: bool
    status_code: int
    headers: Mapping[str, str]


class PdfFetch:
    """One upstream PDF response whose headers are already available."""

    def __init__(
        self,
        probe: PdfProbe,
        *,
        client: httpx.AsyncClient | None = None,
        response: httpx.Response | None = None,
    ):
        self.probe = probe
        self._client = client
        self._response = response

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        if self._response is None:
            return
        async for chunk in self._response.aiter_raw():
            yield chunk

    async def close(self) -> None:
        if self._response is not None:
            await self._response.aclose()
            self._response = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _configured_timeout() -> float:
    raw = os.getenv('KNOWLEDGE_BASE_TIMEOUT_SEC', str(DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


class KnowledgeBaseClient:
    """Async transport client for the three existing upstream endpoints."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        configured = base_url if base_url is not None else os.getenv('KNOWLEDGE_BASE_API_URL', '')
        self.base_url = configured.strip().rstrip('/')
        self.timeout = timeout if timeout is not None and timeout > 0 else _configured_timeout()
        self.transport = transport

    async def search(self, payload: Mapping[str, Any]) -> UpstreamSearchResponse:
        """POST an already-adapted upstream search payload."""
        body = await self._request_json(
            'POST',
            '/api/retrieval/search',
            json=dict(payload),
            validate=lambda value: isinstance(value.get('results'), list),
        )
        return cast(UpstreamSearchResponse, body)

    async def paper(self, paper_id: str) -> UpstreamPaperResponse:
        """GET an upstream paper detail using an opaque paper ID."""
        body = await self._request_json(
            'GET',
            '/api/kg/paper',
            params={'paperId': paper_id},
            validate=lambda value: isinstance(value.get('paper_id'), str) and bool(value['paper_id'].strip()),
        )
        return cast(UpstreamPaperResponse, body)

    async def graph(self, paper_id: str, depth: int = 1) -> UpstreamGraphResponse:
        """GET an upstream paper graph using an opaque paper ID."""
        body = await self._request_json(
            'GET',
            '/api/kg/graph',
            params={'paperId': paper_id, 'depth': depth},
            validate=lambda value: (
                isinstance(value.get('rootId'), str)
                and bool(value['rootId'].strip())
                and isinstance(value.get('nodes'), list)
                and isinstance(value.get('lines'), list)
            ),
        )
        return cast(UpstreamGraphResponse, body)

    async def fetch_pdf(
        self, url: str, *, range_header: str | None = None
    ) -> PdfFetch:
        """Open one PDF response and classify it from response headers."""
        _validate_pdf_url(url)
        validated_range = (
            _validate_pdf_range(range_header) if range_header is not None else None
        )
        client = httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
            follow_redirects=False,
        )
        headers = {'Accept-Encoding': 'identity'}
        if validated_range is not None:
            headers['Range'] = validated_range
        current_url = url
        try:
            for redirect_count in range(MAX_PDF_REDIRECTS + 1):
                request = client.build_request('GET', current_url, headers=headers)
                response = await client.send(request, stream=True)
                if response.status_code not in PDF_REDIRECT_STATUSES:
                    break

                location = response.headers.get('location')
                if not location or redirect_count == MAX_PDF_REDIRECTS:
                    break

                next_url = urljoin(current_url, location)
                await response.aclose()
                try:
                    _validate_pdf_url(next_url)
                except KnowledgeIntegrationError:
                    await client.aclose()
                    raise
                current_url = next_url
        except httpx.TimeoutException as exc:
            await client.aclose()
            raise KnowledgeIntegrationError.timeout() from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            await client.aclose()
            raise KnowledgeIntegrationError.connection_unavailable() from exc
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
            await client.aclose()
            raise KnowledgeIntegrationError.invalid_configuration() from exc
        except httpx.HTTPError as exc:
            await client.aclose()
            raise KnowledgeIntegrationError.request_failed() from exc

        probe = _classify_pdf_response(response)
        if probe.status != 'available':
            await response.aclose()
            await client.aclose()
            return PdfFetch(probe)
        return PdfFetch(probe, client=client, response=response)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        validate: Callable[[dict[str, Any]], bool] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        response: httpx.Response | None = None

        try:
            if not self.base_url:
                raise KnowledgeIntegrationError.not_configured()

            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    transport=self.transport,
                ) as client:
                    response = await client.request(method, f'{self.base_url}{path}', **kwargs)
            except httpx.TimeoutException as exc:
                raise KnowledgeIntegrationError.timeout() from exc
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                raise KnowledgeIntegrationError.connection_unavailable() from exc
            except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
                raise KnowledgeIntegrationError.invalid_configuration() from exc
            except httpx.HTTPError as exc:
                raise KnowledgeIntegrationError.request_failed() from exc

            if response.status_code >= 400:
                raise self._status_error(response.status_code)

            try:
                body = response.json()
            except (TypeError, ValueError) as exc:
                raise KnowledgeIntegrationError.contract_violation() from exc
            if not isinstance(body, dict) or (validate is not None and not validate(body)):
                raise KnowledgeIntegrationError.contract_violation()
        except KnowledgeIntegrationError as error:
            log_event(logger, logging.ERROR, 'knowledge.request.failed', {
                'provider': 'knowledge_base',
                'operation': f'{method} {path}',
                'status_code': error.status_code,
                'duration_ms': round((perf_counter() - started_at) * 1000),
                'error_type': type(error).__name__,
                'error_code': error.code,
            })
            raise

        log_event(logger, logging.INFO, 'knowledge.request.completed', {
            'provider': 'knowledge_base',
            'operation': f'{method} {path}',
            'status_code': response.status_code,
            'duration_ms': round((perf_counter() - started_at) * 1000),
        })
        return body

    @staticmethod
    def _status_error(status_code: int) -> KnowledgeIntegrationError:
        if status_code == 400:
            return KnowledgeIntegrationError.invalid_argument()
        if status_code == 404:
            return KnowledgeIntegrationError.not_found()
        if status_code == 429:
            return KnowledgeIntegrationError.rate_limited()
        if status_code >= 500:
            return KnowledgeIntegrationError(
                'UPSTREAM_UNAVAILABLE', '知识底座暂不可用', True, 503
            )
        return KnowledgeIntegrationError(
            'UPSTREAM_UNAVAILABLE', '知识底座请求失败', True, 502
        )


def _validate_pdf_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if parsed.scheme.lower() not in {'http', 'https'} or not hostname:
            raise ValueError('unsupported PDF URL')
        parsed.port
    except (TypeError, ValueError) as exc:
        raise KnowledgeIntegrationError.invalid_configuration() from exc

    hostname = hostname.lower().rstrip('.')
    if hostname == 'localhost':
        raise KnowledgeIntegrationError.invalid_configuration()
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        or address.is_multicast
    ):
        raise KnowledgeIntegrationError.invalid_configuration()


def _is_pdf_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    return content_type.split(';', 1)[0].strip().lower() == 'application/pdf'


def _validate_pdf_range(value: str) -> str:
    value = value.strip()
    if not value.startswith('bytes=') or ',' in value:
        raise KnowledgeIntegrationError.invalid_argument()

    spec = value.removeprefix('bytes=')
    if spec.startswith('-'):
        valid = spec[1:].isdigit()
    else:
        start, separator, end = spec.partition('-')
        valid = bool(separator) and start.isdigit() and (not end or end.isdigit())
    if not valid:
        raise KnowledgeIntegrationError.invalid_argument()
    return value


def _classify_pdf_response(response: httpx.Response) -> PdfProbe:
    status_code = response.status_code
    headers = dict(response.headers)
    if status_code in (401, 403):
        return PdfProbe('external_only', False, status_code, headers)
    if status_code >= 500:
        return PdfProbe('unavailable', True, status_code, headers)
    if not 200 <= status_code < 300:
        return PdfProbe('unavailable', False, status_code, headers)
    if not _is_pdf_content_type(response.headers.get('content-type')):
        return PdfProbe('unavailable', False, status_code, headers)
    return PdfProbe('available', False, status_code, headers)
