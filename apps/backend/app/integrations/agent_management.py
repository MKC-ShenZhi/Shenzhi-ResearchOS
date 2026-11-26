"""Server-only transport for the Agent management role."""
import asyncio
import json
import os
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from agent_contracts.management import Result
from app.core.errors import BusinessError

MAX_BODY = 2 * 1024 * 1024
SAFE_REJECTIONS = {
    'CONFIG_EXTERNAL_APPROVAL_INVALID',
    'MANAGEMENT_OPERATION_CONFLICT', 'ALERT_NOT_FOUND', 'ALERT_STILL_ACTIVE', 'MANAGEMENT_ACTION_UNSUPPORTED',
    'CURSOR_INVALID', 'TIMEZONE_REQUIRED', 'TIME_WINDOW_INVALID', 'RESOURCE_REVISION_CHANGED',
    'RESOURCE_TOO_LARGE', 'RESOURCE_NOT_AVAILABLE', 'RESOURCE_NOT_FOUND', 'AGENT_DATABASE_UNAVAILABLE',
    'WORKER_NOT_OBSERVED', 'TASK_NOT_FOUND', 'RUN_NOT_FOUND', 'PROTOCOL_INVALID',
    'WORKER_EVIDENCE_UNAVAILABLE',
    'CONFIG_WRITE_DISABLED', 'CONFIG_OPERATION_NOT_FOUND', 'CONFIG_REVISION_NOT_FOUND',
    'CONFIG_VALIDATION_NOT_FOUND', 'CONFIG_VALIDATION_REQUIRED', 'CONFIG_ACTIVE_BASE_REQUIRED',
    'CONFIG_CAS_CONFLICT', 'CONFIG_OPERATION_CONFLICT', 'CONFIG_DRAIN_REQUIRED',
    'CONFIG_PROOF_STALE', 'CONFIG_PROOF_TARGET_MISMATCH', 'CONFIG_PROOF_SIGNATURE_INVALID',
    'CONFIG_PROOF_ARTIFACT_MISMATCH', 'CONFIG_DEPLOYMENT_IN_PROGRESS', 'CONFIG_VALIDATION_BASE_CHANGED',
    'CONFIG_POLICY_EVIDENCE_CHANGED', 'CONFIG_ENFORCEMENT_REQUIRED', 'CONFIG_DEPLOYMENT_NOT_FOUND',
    'CONFIG_DEPLOYMENT_ALREADY_TERMINAL', 'CONFIG_DEPLOYMENT_FENCE_CONFLICT', 'CONFIG_ADMISSION_PAUSE_REQUIRED',
    'CONFIG_LEGACY_DEPLOYMENT_REQUIRES_RESTAGE', 'CONFIG_PREPARATION_REQUIRED', 'CONFIG_APPROVAL_REQUIRED', 'CONFIG_APPROVER_MUST_BE_DISTINCT', 'CONFIG_ADMISSION_FENCE_CONFLICT', 'CONFIG_DEPLOYMENT_OWNS_ADMISSION', 'RESOURCE_NOT_REGISTERED_FOR_REVISION',
}


def management_path(template, params):
    path = template
    for name, value in params.items():
        if (not value or len(value) > 255 or '\\' in value or any(ord(char) < 32 for char in value)
                or any(part in ('', '.', '..') for part in value.split('/'))):
            raise BusinessError(20001, '无效的管理资源 ID', 422)
        path = path.replace('{' + name + '}', quote(value, safe=''))
        path = path.replace('{' + name + ':path}', quote(value, safe='/'))
    return path


async def read(path, response_type, query):
    return await request('GET', path, response_type, query=query)


async def request(method, path, response_type, *, query=None, payload=None, config_role=False):
    origin = os.getenv('AGENT_INTERNAL_URL', '').rstrip('/')
    token = os.getenv('AGENT_CONFIG_MANAGEMENT_TOKEN' if config_role else 'AGENT_MANAGEMENT_TOKEN', '').strip()
    if not origin or not token:
        raise BusinessError(10002, 'Agent 管理连接未配置', 503)
    try:
        timeout = 9 if method == 'POST' else 5
        async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout - 1, trust_env=False) as client:
            async with client.stream(method, origin + '/internal/v2/management' + path,
                                     headers={'Authorization': f'Bearer {token}'}, params=query, json=payload) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=32_768):
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        raise ValueError('management response exceeds size limit')
                if response.status_code in (403, 404, 409, 422, 503):
                    error = json.loads(body)
                    reason = error.get('error', {}).get('reason_code') if isinstance(error, dict) else None
                    if isinstance(reason, str) and reason in SAFE_REJECTIONS:
                        raise BusinessError(20001, reason, response.status_code)
                response.raise_for_status()
        return Result[response_type].model_validate_json(body).data
    except (httpx.HTTPError, TimeoutError, ValidationError, ValueError, TypeError, AttributeError):
        raise BusinessError(10002, 'Agent 管理服务不可用或响应无效', 503) from None
