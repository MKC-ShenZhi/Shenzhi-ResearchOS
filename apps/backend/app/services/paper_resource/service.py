"""Provider-based orchestration for paper PDF resources."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence

import httpx

from app.core.config import paper_resource_config
from app.schemas.paper_resource import PaperResource
from app.services.paper_resource.providers.base import (
    PDFProvider,
    ProviderFetch,
    ProviderValidation,
    normalize_public_http_url,
)
from app.services.paper_resource.providers.http import HTTPProvider
from app.services.paper_resource.providers.openreview import OpenReviewProvider


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
        self.providers = (OpenReviewProvider(http_provider), http_provider)

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

        try:
            fetch = await provider.open(normalized, range_header=range_header)
        except Exception:
            return PaperResourceFetch(PaperResource(
                url=normalized,
                provider=provider.name,
                status='unavailable',
                reason='resource_unavailable',
            ))
        return PaperResourceFetch(
            self._resource(provider, fetch.validation),
            provider_fetch=fetch,
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
    ):
        self.resource = resource
        self._provider_fetch = provider_fetch

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
        async for chunk in self._provider_fetch.iter_bytes():
            yield chunk

    async def close(self) -> None:
        if self._provider_fetch is not None:
            await self._provider_fetch.close()


async def resolve_paper_resource(pdf_url: str | None) -> PaperResource:
    """Convenience entry point for callers that do not need dependency injection."""
    return await PaperResourceService().resolve_paper_resource(pdf_url)
