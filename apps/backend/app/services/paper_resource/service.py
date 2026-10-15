"""Provider-based orchestration for paper PDF resources."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
import re

import httpx

from app.core.config import paper_resource_config
from app.schemas.paper_resource import PaperResource
from app.integrations.paper_resource.base import (
    PDFProvider,
    ProviderFetch,
    ProviderValidation,
    normalize_public_http_url,
)
from app.integrations.paper_resource.http import HTTPProvider
from app.integrations.paper_resource.openreview import OpenReviewProvider

_CONTENT_RANGE = re.compile(r'^bytes\s+(\d+)-(\d+)/(\d+|\*)$', re.IGNORECASE)
_MAX_FETCH_ATTEMPTS = 3


def _body_span(validation: ProviderValidation) -> tuple[int, int, int | None] | None:
    """Return the byte span promised by a PDF response, when known."""
    headers = validation.headers or {}
    if validation.status_code == 206:
        match = _CONTENT_RANGE.fullmatch(headers.get('content-range', '').strip())
        if match is None:
            return None
        start, end = int(match[1]), int(match[2])
        total = None if match[3] == '*' else int(match[3])
        return (start, end, total) if end >= start else None
    if validation.status_code == 200:
        try:
            length = int(headers.get('content-length', ''))
        except ValueError:
            return None
        return (0, length - 1, length) if length > 0 else None
    return None


def _retryable_fetch(validation: ProviderValidation) -> bool:
    return (
        validation.reason in {'request_timeout', 'resource_unavailable'}
        and (validation.status_code is None or validation.status_code >= 500)
    )


class PaperResourceService:
    """Select a provider and return a non-throwing browser resource result."""

    def __init__(
        self,
        providers: Sequence[PDFProvider] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if providers is not None:
            self.providers = tuple(providers)
            return

        config = paper_resource_config()
        http_provider = HTTPProvider(
            timeout=config.timeout_seconds,
            max_size_bytes=config.max_size_bytes,
            transport=transport,
        )
        self.providers = (
            OpenReviewProvider(
                http_provider,
                api_base_url=config.openreview_api_base_url,
                username=config.openreview_username,
                password=config.openreview_password,
            ),
            http_provider,
        )

    async def resolve_paper_resource(self, pdf_url: str | None) -> PaperResource:
        normalized = normalize_public_http_url(pdf_url or '')
        if normalized is None:
            return PaperResource(
                url=None,
                provider='http',
                status='unavailable',
                reason='invalid_pdf_url',
            )

        provider = next(
            (candidate for candidate in self.providers if candidate.match(normalized)),
            None,
        )
        if provider is None:
            return PaperResource(
                url=None,
                provider='http',
                status='unavailable',
                reason='invalid_pdf_url',
            )

        try:
            validation = await provider.validate(normalized)
        except Exception:
            # Resource validation is deliberately best-effort: a broken source
            # must not make the paper detail endpoint fail.
            return PaperResource(
                url=normalized,
                provider=provider.name,
                status='unavailable',
                reason='resource_unavailable',
            )
        return self._resource(provider, validation)

    async def open_paper_resource(
        self,
        pdf_url: str | None,
        *,
        range_header: str | None = None,
    ) -> 'PaperResourceFetch':
        normalized = normalize_public_http_url(pdf_url or '')
        if normalized is None:
            return PaperResourceFetch(PaperResource(
                url=None,
                provider='http',
                status='unavailable',
                reason='invalid_pdf_url',
            ))

        provider = next(
            (candidate for candidate in self.providers if candidate.match(normalized)),
            None,
        )
        if provider is None:
            return PaperResourceFetch(PaperResource(
                url=None,
                provider='http',
                status='unavailable',
                reason='invalid_pdf_url',
            ))

        for attempt in range(_MAX_FETCH_ATTEMPTS):
            try:
                fetch = await provider.open(normalized, range_header=range_header)
            except Exception:
                if attempt + 1 < _MAX_FETCH_ATTEMPTS:
                    continue
                return PaperResourceFetch(PaperResource(
                    url=normalized,
                    provider=provider.name,
                    status='unavailable',
                    reason='resource_unavailable',
                ))
            if not _retryable_fetch(fetch.validation) or attempt + 1 == _MAX_FETCH_ATTEMPTS:
                break
            await fetch.close()
        return PaperResourceFetch(
            self._resource(provider, fetch.validation),
            provider_fetch=fetch,
            provider=provider,
            source_url=normalized,
        )

    @staticmethod
    def _resource(
        provider: PDFProvider,
        validation: ProviderValidation,
    ) -> PaperResource:
        return PaperResource(
            url=validation.url,
            provider=provider.name,
            status='available' if validation.available else 'unavailable',
            reason=validation.reason,
        )


class PaperResourceFetch:
    """Resolved resource plus an optional live upstream response."""

    def __init__(
        self,
        resource: PaperResource,
        *,
        provider_fetch: ProviderFetch | None = None,
        provider: PDFProvider | None = None,
        source_url: str | None = None,
    ):
        self.resource = resource
        self._provider_fetch = provider_fetch
        self._provider = provider
        self._source_url = source_url

    @property
    def status_code(self) -> int | None:
        if self._provider_fetch is None:
            return None
        return self._provider_fetch.validation.status_code

    @property
    def headers(self) -> Mapping[str, str]:
        if self._provider_fetch is None:
            return {}
        return self._provider_fetch.validation.headers or {}

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        if self._provider_fetch is None:
            return
        span = _body_span(self._provider_fetch.validation)
        if span is None or self._provider is None or self._source_url is None:
            async for chunk in self._provider_fetch.iter_bytes():
                yield chunk
            return

        start, end, total = span
        expected = end - start + 1
        delivered = 0
        last_error: httpx.TransportError | None = None
        for attempt in range(_MAX_FETCH_ATTEMPTS):
            try:
                async for chunk in self._provider_fetch.iter_bytes():
                    remaining = expected - delivered
                    if remaining <= 0:
                        break
                    part = chunk[:remaining]
                    delivered += len(part)
                    yield part
            except httpx.TransportError as error:
                last_error = error
            if delivered == expected:
                return
            if attempt + 1 == _MAX_FETCH_ATTEMPTS:
                raise httpx.RemoteProtocolError('PDF upstream response ended before its promised byte range') from last_error

            await self._provider_fetch.close()
            next_start = start + delivered
            continuation = None
            for request_attempt in range(_MAX_FETCH_ATTEMPTS):
                try:
                    candidate = await self._provider.open(
                        self._source_url,
                        range_header=f'bytes={next_start}-{end}',
                    )
                except Exception:
                    if request_attempt + 1 == _MAX_FETCH_ATTEMPTS:
                        raise
                    continue
                if _retryable_fetch(candidate.validation) and request_attempt + 1 < _MAX_FETCH_ATTEMPTS:
                    await candidate.close()
                    continue
                continuation = candidate
                break
            assert continuation is not None
            continued_span = _body_span(continuation.validation)
            if (
                not continuation.validation.available
                or continuation.validation.status_code != 206
                or continued_span is None
                or continued_span[0] != next_start
                or continued_span[1] > end
                or continued_span[2] != total
            ):
                await continuation.close()
                raise httpx.RemoteProtocolError('PDF upstream did not honor the resume byte range')
            self._provider_fetch = continuation

    async def close(self) -> None:
        if self._provider_fetch is not None:
            await self._provider_fetch.close()


async def resolve_paper_resource(pdf_url: str | None) -> PaperResource:
    """Convenience entry point for callers that do not need dependency injection."""
    return await PaperResourceService().resolve_paper_resource(pdf_url)
