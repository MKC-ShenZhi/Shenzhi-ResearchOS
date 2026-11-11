"""Backend-to-Agent service authentication."""
from __future__ import annotations

import hmac
import os

from fastapi import Header

from agent_app.errors import BusinessError


async def require_service(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv('AGENT_SERVICE_TOKEN', '').strip()
    if not expected:
        raise BusinessError(20004, 'Agent 服务凭据未配置', 503)
    supplied = authorization or ''
    if not supplied.startswith('Bearer ') or not hmac.compare_digest(supplied[7:], expected):
        raise BusinessError(20004, '服务身份验证失败', 401)
