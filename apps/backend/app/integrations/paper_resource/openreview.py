"""OpenReview authenticated PDF access with API v2-to-v1 fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import os
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from openreview.api import OpenReviewClient

from app.core.config import normalize_openreview_api_base_url
from app.core.logging import log_event
from app.integrations.paper_resource.base import (
    PDFProvider,
    ProviderFetch,
    ProviderValidation,
)
from app.integrations.paper_resource.http import HTTPProvider


LEGACY_API_BASE_URL = 'https://api.openreview.net'
AUTH_FAILURE_STATUSES = {401, 403}
ClientFactory = Callable[..., object]

logger = logging.getLogger(__name__)


class OpenReviewProvider(PDFProvider):
    name = 'openreview'

    def __init__(
        self,
        http_provider: HTTPProvider,
        *,
        api_base_url: str = 'https://api2.openreview.net',
        username: str = '',
        password: str = '',
        client_factory: ClientFactory = OpenReviewClient,
    ):
        self.http_provider = http_provider
        self.api_base_url = normalize_openreview_api_base_url(api_base_url)
        self.username = username.strip()
        self.password = password
        self._client_factory = client_factory
        self._client: object | None = None
        self._client_lock = asyncio.Lock()

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

        token = await self._get_token()
        if (self.username or self.password) and token is None:
            return ProviderFetch(ProviderValidation(
                url=_api_pdf_url(self.api_base_url, note_id),
                reason='resource_unavailable',
            ))

        fetch, token, auth_retried = await self._open_api_with_auth_retry(
            note_id,
            api_version='v2',
            api_base_url=self.api_base_url,
            token=token,
            range_header=range_header,
            allow_auth_retry=True,
        )
        if fetch.validation.available or _preserve_failure(fetch.validation):
            return fetch
        if fetch.validation.status_code != 404:
            return fetch

        await fetch.close()
        fetch, _, _ = await self._open_api_with_auth_retry(
            note_id,
            api_version='v1',
            api_base_url=LEGACY_API_BASE_URL,
            token=token,
            range_header=range_header,
            allow_auth_retry=not auth_retried,
        )
        return fetch

    async def _open_api_with_auth_retry(
        self,
        note_id: str,
        *,
        api_version: str,
        api_base_url: str,
        token: str | None,
        range_header: str | None,
        allow_auth_retry: bool,
    ) -> tuple[ProviderFetch, str | None, bool]:
        fetch = await self._open_api(
            note_id,
            api_version=api_version,
            api_base_url=api_base_url,
            token=token,
            range_header=range_header,
        )
        if (
            fetch.validation.status_code not in AUTH_FAILURE_STATUSES
            or not allow_auth_retry
            or not (self.username or self.password)
        ):
            return fetch, token, False

        await fetch.close()
        refreshed_token = await self._refresh_token(token)
        if refreshed_token is None:
            return fetch, token, True

        fetch = await self._open_api(
            note_id,
            api_version=api_version,
            api_base_url=api_base_url,
            token=refreshed_token,
            range_header=range_header,
        )
        if fetch.validation.status_code in AUTH_FAILURE_STATUSES:
            await self._clear_client(refreshed_token)
        return fetch, refreshed_token, True

    async def _open_api(
        self,
        note_id: str,
        *,
        api_version: str,
        api_base_url: str,
        token: str | None,
        range_header: str | None,
    ) -> ProviderFetch:
        headers = {'Authorization': f'Bearer {token}'} if token else None
        fetch = await self.http_provider.open_with_headers(
            _api_pdf_url(api_base_url, note_id),
            range_header=range_header,
            extra_headers=headers,
        )
        _log_attempt(
            note_id=note_id,
            api_version=api_version,
            authenticated=token is not None,
            status_code=fetch.validation.status_code,
        )
        return fetch

    async def _get_token(self) -> str | None:
        if not (self.username or self.password):
            return None
        async with self._client_lock:
            if self._client is not None:
                return _client_token(self._client)
            return await self._create_client()

    async def _refresh_token(self, rejected_token: str | None) -> str | None:
        async with self._client_lock:
            current_token = _client_token(self._client)
            if current_token is not None and current_token != rejected_token:
                return current_token
            self._client = None
            return await self._create_client()

    async def _clear_client(self, rejected_token: str) -> None:
        async with self._client_lock:
            if _client_token(self._client) == rejected_token:
                self._client = None

    async def _create_client(self) -> str | None:
        try:
            client = await asyncio.to_thread(
                self._client_factory,
                baseurl=self.api_base_url,
                username=self.username,
                password=self.password,
            )
        except Exception as error:
            _log_auth_failure(error)
            return None
        self._client = client
        return _client_token(client)


def _client_token(client: object | None) -> str | None:
    token = getattr(client, 'token', None)
    if not isinstance(token, str) or not token.strip():
        return None
    return token.removeprefix('Bearer ').strip() or None


def _log_attempt(
    *,
    note_id: str,
    api_version: str,
    authenticated: bool,
    status_code: int | None,
) -> None:
    if (os.getenv('ENVIRONMENT') or 'development').strip().lower() != 'development':
        return
    log_event(
        logger,
        logging.INFO,
        'paper_resource.openreview_attempt',
        {
            'note_id': note_id,
            'api_version': api_version,
            'authenticated': authenticated,
            'status_code': status_code,
        },
    )


def _log_auth_failure(error: Exception) -> None:
    if (os.getenv('ENVIRONMENT') or 'development').strip().lower() != 'development':
        return
    log_event(
        logger,
        logging.INFO,
        'paper_resource.openreview_auth_failed',
        {'error_type': type(error).__name__},
    )


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


def _api_pdf_url(api_base_url: str, note_id: str) -> str:
    return f'{api_base_url}/pdf?{urlencode({"id": note_id})}'


def _preserve_failure(validation: ProviderValidation) -> bool:
    return validation.status_code == 416 or validation.reason == 'pdf_too_large'
