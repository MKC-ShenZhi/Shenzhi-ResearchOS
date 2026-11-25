"""Authenticated Backend-to-Agent HTTP boundary."""
from __future__ import annotations

import os
from typing import Any

import httpx
from agent_contracts import (
    OwnerQueryWire, PlatformEventWire, RunEventsQueryWire,
    RunRecordWire, RunSteerRequestWire, RunSteerResponseWire,
    TaskRecordWire, TaskRunsResponseWire,
)

from app.core.errors import BusinessError


class AgentGateway:
    def __init__(self, *, base_url: str | None = None, token: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = (base_url or os.getenv('AGENT_INTERNAL_URL', 'http://127.0.0.1:8101')).rstrip('/')
        self.token = token if token is not None else os.getenv('AGENT_SERVICE_TOKEN', '').strip()
        self.transport = transport

    async def request(self, method: str, path: str, *, params: dict | None = None,
                      payload: dict | None = None) -> dict[str, Any]:
        if not self.token:
            raise BusinessError(20004, 'Agent 服务凭据未配置', 503)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=20.0,
                                         transport=self.transport,
                                         # Internal service traffic must not inherit the
                                         # editor's Internet proxy (or leak its Bearer).
                                         trust_env=False,
                                         headers={'Authorization': f'Bearer {self.token}'}) as client:
                response = await client.request(method, path, params=params, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BusinessError(20004, 'Agent 服务暂不可用，请稍后重试', 503) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.is_error:
            error = data.get('error') if isinstance(data, dict) else None
            if not isinstance(error, dict) and isinstance(data, dict):
                error = data
            message = error.get('message') if isinstance(error, dict) else None
            code = error.get('code') if isinstance(error, dict) else None
            raise BusinessError(int(code or 20004), str(message or 'Agent 服务请求失败'),
                                response.status_code)
        if not isinstance(data, dict):
            raise BusinessError(20004, 'Agent 服务返回格式无效', 502)
        return data

    async def task(self, task_id: str, owner: str) -> dict[str, Any]:
        query = OwnerQueryWire(owner_id=owner)
        result = await self.request('GET', f'/internal/v1/tasks/{task_id}',
                                    params=query.model_dump(mode='json'))
        return TaskRecordWire.model_validate(result).model_dump(mode='json')

    async def run(self, run_id: str, owner: str) -> dict[str, Any]:
        query = OwnerQueryWire(owner_id=owner)
        result = await self.request('GET', f'/internal/v1/runs/{run_id}',
                                    params=query.model_dump(mode='json'))
        return RunRecordWire.model_validate(result).model_dump(mode='json')

    async def task_runs(self, task_id: str, owner: str) -> list[str]:
        query = OwnerQueryWire(owner_id=owner)
        result = await self.request('GET', f'/internal/v1/tasks/{task_id}/runs',
                                    params=query.model_dump(mode='json'))
        return TaskRunsResponseWire.model_validate(result).run_ids

    async def events(self, run_id: str, owner: str, after_seq: int) -> list[dict[str, Any]]:
        query = RunEventsQueryWire(owner_id=owner, after_seq=after_seq)
        result = await self.request('GET', f'/internal/v1/runs/{run_id}/events',
                                    params=query.model_dump(mode='json'))
        return [PlatformEventWire.model_validate(item).model_dump(mode='json')
                for item in result.get('events') or []]

    async def cancel(self, task_id: str, owner: str) -> dict[str, Any]:
        query = OwnerQueryWire(owner_id=owner)
        result = await self.request('POST', f'/internal/v1/tasks/{task_id}/cancel',
                                    params=query.model_dump(mode='json'))
        return TaskRecordWire.model_validate(result).model_dump(mode='json')

    async def steer(self, run_id: str, owner: str, message: str) -> dict[str, Any]:
        body = RunSteerRequestWire(owner_id=owner, text=message)
        result = await self.request(
            'POST', f'/internal/v1/runs/{run_id}/steer',
            payload=body.model_dump(mode='json'),
        )
        return RunSteerResponseWire.model_validate(result).model_dump(mode='json')

async def read_run_update(gateway: AgentGateway, run_id: str, owner: str,
                          after_seq: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read status before events so a terminal report cannot truncate the tail.

    Control seals a Run against event writes when it commits its report. If this
    read observes that report, the subsequent events read includes its full tail.
    If it does not, the caller must poll again instead of emitting a result.
    """
    run = await gateway.run(run_id, owner)
    events = await gateway.events(run_id, owner, after_seq)
    return run, events


agent_gateway = AgentGateway()
