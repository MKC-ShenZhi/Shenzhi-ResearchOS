"""OpenReview authenticated PDF access with a public endpoint fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

import httpx

from app.integrations.paper_resource.base import (
    PDFProvider,
    ProviderFetch,
    ProviderValidation,
)
from app.integrations.paper_resource.http import HTTPProvider


class OpenReviewProvider(PDFProvider):
    name = 'openreview'

    def __init__(
        self,
        http_provider: HTTPProvider,
        *,
        api_base_url: str = 'https://api2.openreview.net',
        username: str = '',
        password: str = '',
    ):
        self.http_provider = http_provider
        self.api_base_url = api_base_url.strip().rstrip('/')
        self.username = username.strip()
        self.password = password
        self._token: str | None = None
        self._login_lock = asyncio.Lock()

    def match(self, url: str) -> bool:
        try:
            hostname = (urlsplit(url).hostname or '').lower().rstrip('.')
        except (TypeError, ValueError):
            return False
        return hostname == 'openreview.net' or hostname.endswith('.openreview.net')

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
        note_id = _note_id(url)
        if note_id is None:
            return await self.http_provider.open(url, range_header=range_header)

        public_url = _public_pdf_url(note_id)
        if not self.username or not self.password:
            return await self.http_provider.open(public_url, range_header=range_header)

        token = await self._get_token()
        if token is None:
            return await self.http_provider.open(public_url, range_header=range_header)

        fetch = await self._open_authenticated(note_id, token, range_header)
        if fetch.validation.available or _preserve_failure(fetch.validation):
            return fetch

        if fetch.validation.status_code in (401, 403):
            await fetch.close()
            token = await self._refresh_token(token)
            if token is not None:
                fetch = await self._open_authenticated(note_id, token, range_header)
                if fetch.validation.available or _preserve_failure(fetch.validation):
                    return fetch
                if fetch.validation.status_code in (401, 403):
                    await self._clear_token(token)

        await fetch.close()
        return await self.http_provider.open(public_url, range_header=range_header)

    async def _open_authenticated(
        self,
        note_id: str,
        token: str,
        range_header: str | None,
    ) -> ProviderFetch:
        return await self.http_provider.open_with_headers(
            _api_pdf_url(self.api_base_url, note_id),
            range_header=range_header,
            extra_headers={'Authorization': f'Bearer {token}'},
        )

    async def _get_token(self) -> str | None:
        if self._token is not None:
            return self._token
        async with self._login_lock:
            if self._token is None:
                self._token = await self._login()
            return self._token

    async def _refresh_token(self, rejected_token: str) -> str | None:
        async with self._login_lock:
            if self._token is not None and self._token != rejected_token:
                return self._token
            self._token = None
            self._token = await self._login()
            return self._token

    async def _clear_token(self, rejected_token: str) -> None:
        async with self._login_lock:
            if self._token == rejected_token:
                self._token = None

    async def _login(self) -> str | None:
        if not self.api_base_url:
            return None
        try:
            async with httpx.AsyncClient(
                timeout=self.http_provider.timeout,
                transport=self.http_provider.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    f'{self.api_base_url}/login',
                    json={
                        'id': self.username,
                        'password': self.password,
                        'expiresIn': None,
                    },
                    headers={'Accept': 'application/json'},
                )
            if not 200 <= response.status_code < 300:
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if not isinstance(payload, Mapping):
            return None
        token = payload.get('token')
        if isinstance(token, str) and token.strip():
            return token.strip()
        # OpenReview's current client starts an interactive MFA flow when
        # mfaPending is present. A backend request cannot complete that flow.
        return None


def _note_id(url: str) -> str | None:
    """Extract a note id only from known OpenReview PDF/forum URL shapes."""
    parsed = urlsplit(url)
    hostname = (parsed.hostname or '').lower().rstrip('.')
    if hostname != 'openreview.net' and not hostname.endswith('.openreview.net'):
        return None

    path = parsed.path.rstrip('/') or '/'
    if path in {'/forum', '/pdf'}:
        note_ids = [
            value
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            if name == 'id'
        ]
        return _clean_note_id(note_ids[0]) if len(note_ids) == 1 else None

    if path.startswith('/pdf/') and path.count('/') == 2:
        return _clean_note_id(unquote(path.removeprefix('/pdf/')), path_value=True)
    return None


def _clean_note_id(value: str | None, *, path_value: bool = False) -> str | None:
    if value is None or not value or value != value.strip() or len(value) > 512:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    if path_value and '/' in value:
        return None
    return value


def _public_pdf_url(note_id: str) -> str:
    return f'https://openreview.net/pdf?{urlencode({"id": note_id})}'


def _api_pdf_url(api_base_url: str, note_id: str) -> str:
    return f'{api_base_url}/pdf?{urlencode({"id": note_id})}'


def _preserve_failure(validation: ProviderValidation) -> bool:
    return validation.status_code == 416 or validation.reason == 'pdf_too_large'
