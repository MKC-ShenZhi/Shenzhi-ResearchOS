"""Provider abstraction and shared URL safety checks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
import ipaddress
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

from app.schemas.paper_resource import PaperResourceProvider, PaperResourceReason


@dataclass(frozen=True)
class ProviderValidation:
    url: str
    reason: PaperResourceReason | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    status_code: int | None = None
    headers: Mapping[str, str] | None = None

    @property
    def available(self) -> bool:
        return self.reason is None


class PDFProvider(ABC):
    """Resolve provider-specific URLs and validate their PDF response headers."""

    name: PaperResourceProvider

    @abstractmethod
    def match(self, url: str) -> bool:
        """Return whether this provider owns the URL."""

    @abstractmethod
    async def validate(self, url: str) -> ProviderValidation:
        """Return a safe validation result without raising transport errors."""

    async def open(
        self,
        url: str,
        *,
        range_header: str | None = None,
    ) -> 'ProviderFetch':
        """Open a validated response for streaming when the provider supports it."""
        return ProviderFetch(await self.validate(url))


class ProviderFetch:
    """An opened upstream response owned by a provider until explicitly closed."""

    def __init__(
        self,
        validation: ProviderValidation,
        *,
        client: httpx.AsyncClient | None = None,
        response: httpx.Response | None = None,
    ):
        self.validation = validation
        self._client = client
        self._response = response

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        if self._response is None:
            return
        if self._response.is_stream_consumed:
            # Mock/in-memory transports may eagerly buffer the response even
            # when the client requested streaming. Real network responses take
            # the raw streaming branch below.
            yield self._response.content
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


def normalize_public_http_url(value: str) -> str | None:
    """Normalize an HTTP URL and reject obvious local-network targets."""
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        parsed.port
    except (TypeError, ValueError):
        return None

    if parsed.scheme.lower() not in {'http', 'https'} or not hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None

    hostname = hostname.lower().rstrip('.')
    if hostname == 'localhost' or hostname.endswith('.localhost'):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
            or address.is_multicast
        ):
            return None

    host = hostname
    if ':' in hostname:
        host = f'[{hostname}]'
    if parsed.port is not None:
        host = f'{host}:{parsed.port}'
    normalized = SplitResult(
        parsed.scheme.lower(),
        host,
        parsed.path or '/',
        parsed.query,
        '',
    )
    return urlunsplit(normalized)
