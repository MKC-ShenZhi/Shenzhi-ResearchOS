"""Default validator for public HTTP(S) PDF resources."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx

from app.services.paper_resource.providers.base import (
    PDFProvider,
    ProviderFetch,
    ProviderValidation,
    normalize_public_http_url,
)


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 3
_CONTENT_RANGE_TOTAL = re.compile(r'^bytes\s+\d+-\d+/(\d+|\*)$', re.IGNORECASE)


class HTTPProvider(PDFProvider):
    """Probe a PDF with a one-byte range request and inspect response headers."""

    name = 'http'

    def __init__(
        self,
        *,
        timeout: float,
        max_size_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.timeout = timeout
        self.max_size_bytes = max_size_bytes
        self.transport = transport

    def match(self, url: str) -> bool:
        return normalize_public_http_url(url) is not None

    async def validate(self, url: str) -> ProviderValidation:
        fetch = await self.open(url, range_header='bytes=0-0')
        try:
            return fetch.validation
        finally:
            await fetch.close()

    async def open(
        self,
        url: str,
        *,
        range_header: str | None = None,
    ) -> ProviderFetch:
        normalized = normalize_public_http_url(url)
        if normalized is None:
            return ProviderFetch(ProviderValidation(
                url=url,
                reason='invalid_pdf_url',
            ))

        client = httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
            follow_redirects=False,
        )

        try:
            response, final_url = await self._request(
                client,
                normalized,
                range_header=range_header,
            )
            if response is None:
                await client.aclose()
                return ProviderFetch(ProviderValidation(
                    url=final_url,
                    reason='resource_unavailable',
                ))
            validation = self._classify(final_url, response)
            if not validation.available:
                await response.aclose()
                await client.aclose()
                return ProviderFetch(validation)
            return ProviderFetch(
                validation,
                client=client,
                response=response,
            )
        except httpx.TimeoutException:
            await client.aclose()
            return ProviderFetch(ProviderValidation(
                url=normalized,
                reason='request_timeout',
            ))
        except (httpx.HTTPError, ValueError):
            await client.aclose()
            return ProviderFetch(ProviderValidation(
                url=normalized,
                reason='resource_unavailable',
            ))

    async def _request(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        range_header: str | None,
    ) -> tuple[httpx.Response | None, str]:
        current_url = url
        headers = {
            'Accept': 'application/pdf',
            'Accept-Encoding': 'identity',
        }
        if range_header is not None:
            headers['Range'] = _validate_pdf_range(range_header)
        for redirect_count in range(MAX_REDIRECTS + 1):
            request = client.build_request('GET', current_url, headers=headers)
            response = await client.send(request, stream=True)
            if response.status_code not in REDIRECT_STATUSES:
                return response, current_url

            location = response.headers.get('location')
            if not location or redirect_count == MAX_REDIRECTS:
                await response.aclose()
                return None, current_url

            next_url = normalize_public_http_url(urljoin(current_url, location))
            await response.aclose()
            if next_url is None:
                return None, current_url
            current_url = next_url
        return None, current_url

    def _classify(self, url: str, response: httpx.Response) -> ProviderValidation:
        headers = dict(response.headers)
        if not 200 <= response.status_code < 300:
            return ProviderValidation(
                url=url,
                reason='resource_unavailable',
                status_code=response.status_code,
                headers=headers,
            )

        content_type = _content_type(response.headers.get('content-type'))
        if content_type is not None and content_type != 'application/pdf':
            return ProviderValidation(
                url=url,
                reason='invalid_content_type',
                content_type=content_type,
                status_code=response.status_code,
                headers=headers,
            )

        size_bytes = _resource_size(response)
        if size_bytes is not None and size_bytes > self.max_size_bytes:
            return ProviderValidation(
                url=url,
                reason='pdf_too_large',
                content_type=content_type,
                size_bytes=size_bytes,
                status_code=response.status_code,
                headers=headers,
            )
        return ProviderValidation(
            url=url,
            content_type=content_type,
            size_bytes=size_bytes,
            status_code=response.status_code,
            headers=headers,
        )


def _validate_pdf_range(value: str) -> str:
    value = value.strip()
    if not value.startswith('bytes=') or ',' in value:
        raise ValueError('invalid PDF range')

    spec = value.removeprefix('bytes=')
    if spec.startswith('-'):
        valid = spec[1:].isdigit()
    else:
        start, separator, end = spec.partition('-')
        valid = bool(separator) and start.isdigit() and (not end or end.isdigit())
    if not valid:
        raise ValueError('invalid PDF range')
    return value


def _content_type(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.split(';', 1)[0].strip().lower() or None


def _positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None


def _resource_size(response: httpx.Response) -> int | None:
    content_range = response.headers.get('content-range')
    if content_range:
        match = _CONTENT_RANGE_TOTAL.fullmatch(content_range.strip())
        if match and match.group(1) != '*':
            return _positive_int(match.group(1))
    return _positive_int(response.headers.get('content-length'))
