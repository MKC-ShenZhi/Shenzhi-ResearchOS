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
    'CURSOR_INVALID', 'RESOURCE_REVISION_CHANGED', 'RESOURCE_TOO_LARGE',
    'RESOURCE_NOT_AVAILABLE', 'RESOURCE_NOT_FOUND', 'PROTOCOL_INVALID',
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
    origin = os.getenv('AGENT_INTERNAL_URL', '').rstrip('/')
    token = os.getenv('AGENT_MANAGEMENT_TOKEN', '').strip()
    if not origin or not token:
        raise BusinessError(10002, 'Agent 管理连接未配置', 503)
    try:
        timeout = 5
        async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout - 1, trust_env=False) as client:
            async with client.stream('GET', origin + '/internal/v2/management' + path,
                                     headers={'Authorization': f'Bearer {token}'}, params=query) as response:
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
