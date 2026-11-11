"""Authenticated Backend-to-Agent HTTP boundary."""
from __future__ import annotations

import base64
import os
from typing import Any

import httpx
from agent_contracts import (
    AgentConfigWire, OwnerQueryWire, PlatformEventWire, RunEventsQueryWire,
    RunRecordWire, RunSteerRequestWire, RunSteerResponseWire,
    SessionFileReadRequestWire, SessionFileReadResponseWire, TaskRecordWire,
    TaskSubmissionWire, WorkspaceClaimCommitResponseWire,
    WorkspaceClaimPrepareResponseWire, WorkspaceClaimRequestWire,
    WorkspaceCreateRequestWire, WorkspaceCreateResponseWire,
    WorkspaceFileWriteRequestWire, WorkspaceFileWriteResponseWire,
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

    async def config(self) -> dict[str, Any]:
        result = await self.request('GET', '/internal/v1/config')
        return AgentConfigWire.model_validate(result).model_dump(mode='json')

    async def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = TaskSubmissionWire.model_validate(payload)
        result = await self.request('POST', '/internal/v1/tasks',
                                    payload=body.model_dump(mode='json'))
        return TaskRecordWire.model_validate(result).model_dump(mode='json')

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

    async def create_workspace(self, owner: str) -> dict[str, Any]:
        body = WorkspaceCreateRequestWire(owner_id=owner)
        result = await self.request(
            'POST', '/internal/v1/workspaces', payload=body.model_dump(mode='json'),
        )
        return WorkspaceCreateResponseWire.model_validate(result).model_dump(mode='json')

    async def prepare_workspace_claim(self, source_owner: str, target_owner: str,
                                     session_ids: list[str]) -> dict[str, Any]:
        body = WorkspaceClaimRequestWire(
            source_owner=source_owner, target_owner=target_owner, session_ids=session_ids,
        )
        result = await self.request(
            'POST', '/internal/v1/workspaces/claim/prepare',
            payload=body.model_dump(mode='json'),
        )
        return WorkspaceClaimPrepareResponseWire.model_validate(result).model_dump(mode='json')

    async def commit_workspace_claim(self, source_owner: str, target_owner: str,
                                    session_ids: list[str]) -> dict[str, Any]:
        body = WorkspaceClaimRequestWire(
            source_owner=source_owner, target_owner=target_owner, session_ids=session_ids,
        )
        result = await self.request(
            'POST', '/internal/v1/workspaces/claim/commit',
            payload=body.model_dump(mode='json'),
        )
        return WorkspaceClaimCommitResponseWire.model_validate(result).model_dump(mode='json')

    async def write_workspace_file(self, workspace_id: str, owner: str,
                                   path: str, content: bytes) -> dict[str, Any]:
        body = WorkspaceFileWriteRequestWire(
            owner_id=owner, workspace_id=workspace_id, path=path,
            content_base64=base64.b64encode(content).decode('ascii'),
        )
        result = await self.request(
            'POST', f'/internal/v1/workspaces/{workspace_id}/files',
            payload=body.model_dump(mode='json'),
        )
        return WorkspaceFileWriteResponseWire.model_validate(result).model_dump(mode='json')

    async def read_session_file(self, owner: str, session_id: str,
                                path: str) -> tuple[bytes, str]:
        query = SessionFileReadRequestWire(owner_id=owner, path=path)
        result = await self.request(
            'GET', f'/internal/v1/sessions/{session_id}/files',
            params=query.model_dump(mode='json'),
        )
        try:
            response = SessionFileReadResponseWire.model_validate(result)
            content = base64.b64decode(response.content_base64, validate=True)
            media_type = response.media_type
        except (KeyError, ValueError, TypeError) as exc:
            raise BusinessError(20004, 'Agent 文件响应无效', 502) from exc
        return content, media_type


agent_gateway = AgentGateway()
