"""HTTP transport boundary for the external Knowledge Base API."""

from __future__ import annotations

import os
import logging
from time import perf_counter
from collections.abc import Callable
from typing import Any, Mapping, cast

import httpx

from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.core.logging import log_event
from app.integrations.knowledge.schemas import (
    UpstreamGraphResponse,
    UpstreamPaperResponse,
    UpstreamSearchResponse,
)


DEFAULT_TIMEOUT_SECONDS = 30.0
logger = logging.getLogger(__name__)


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
