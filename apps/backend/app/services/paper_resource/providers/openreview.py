"""OpenReview URL normalization backed by the generic HTTP validator."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.paper_resource.providers.base import (
    PDFProvider,
    ProviderFetch,
    ProviderValidation,
)
from app.services.paper_resource.providers.http import HTTPProvider


class OpenReviewProvider(PDFProvider):
    name = 'openreview'

    def __init__(self, http_provider: HTTPProvider):
        self.http_provider = http_provider

    def match(self, url: str) -> bool:
        try:
            hostname = (urlsplit(url).hostname or '').lower().rstrip('.')
        except (TypeError, ValueError):
            return False
        return hostname == 'openreview.net' or hostname.endswith('.openreview.net')

    async def validate(self, url: str) -> ProviderValidation:
        return await self.http_provider.validate(_pdf_url(url))

    async def open(
        self,
        url: str,
        *,
        range_header: str | None = None,
    ) -> ProviderFetch:
        return await self.http_provider.open(
            _pdf_url(url),
            range_header=range_header,
        )


def _pdf_url(url: str) -> str:
    """Turn a canonical OpenReview forum URL into its public PDF endpoint."""
    parsed = urlsplit(url)
    if parsed.path.rstrip('/') != '/forum':
        return url

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    note_id = query.get('id')
    if not note_id:
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, '/pdf', urlencode({'id': note_id}), ''))
