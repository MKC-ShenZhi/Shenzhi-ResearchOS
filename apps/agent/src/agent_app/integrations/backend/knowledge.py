"""Agent adapter for Backend-owned Knowledge APIs; no DB or upstream credentials here."""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import httpx
from agent_contracts import (
    KnowledgeGraphQueryWire, KnowledgePaperDetailWire, KnowledgePaperGraphWire,
    KnowledgeSearchRequestWire, KnowledgeSearchResponseWire,
)

from agent_app.errors import BusinessError


class BackendKnowledgeClient:
    def __init__(self):
        self.base_url = os.getenv(
            'BACKEND_INTERNAL_URL', 'http://127.0.0.1:8000/api/v1/agent',
        ).rstrip('/')
        self.token = os.getenv('AGENT_SERVICE_TOKEN', '').strip()

    async def _request(self, method: str, path: str, *, params: dict | None = None,
                       payload: dict | None = None) -> dict[str, Any]:
        if not self.token:
            raise BusinessError(20004, 'Agent 到 Backend 的服务凭据未配置', 503)
        try:
            async with httpx.AsyncClient(timeout=30.0,
                                         headers={'Authorization': f'Bearer {self.token}'}) as client:
                response = await client.request(method, f'{self.base_url}{path}',
                                                params=params, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BusinessError(20004, '知识服务暂不可用', 503) from exc
        if response.is_error:
            raise BusinessError(20004, '知识服务请求失败', response.status_code)
        data = response.json()
        if not isinstance(data, dict):
            raise BusinessError(20004, '知识服务返回格式无效', 502)
        return data

    async def search(self, payload: dict) -> dict[str, Any]:
        request = KnowledgeSearchRequestWire.model_validate(payload)
        response = await self._request(
            'POST', '/internal/knowledge/search',
            payload=request.model_dump(mode='json', by_alias=True),
        )
        return KnowledgeSearchResponseWire.model_validate(response).model_dump(
            mode='json', by_alias=True,
        )

    async def get_paper(self, paper_id: str) -> SimpleNamespace:
        result = await self._request(
            'GET', f'/internal/knowledge/papers/{quote(paper_id, safe="")}',
        )
        result = KnowledgePaperDetailWire.model_validate(result).model_dump(
            mode='json', by_alias=True,
        )
        return SimpleNamespace(**result)

    async def get_graph(self, paper_id: str, *, depth: int = 1) -> dict[str, Any]:
        safe_id = quote(paper_id, safe='')
        query = KnowledgeGraphQueryWire(depth=depth)
        result = await self._request(
            'GET', f'/internal/knowledge/graph/{safe_id}',
            params=query.model_dump(mode='json'),
        )
        return KnowledgePaperGraphWire.model_validate(result).model_dump(
            mode='json', by_alias=True,
        )


backend_knowledge = BackendKnowledgeClient()
