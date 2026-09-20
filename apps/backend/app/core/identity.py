"""Identity supplied by the existing Better Auth BFF, never another login."""
import os
import secrets
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Literal
from uuid import UUID
from fastapi import Request
from app.core.errors import BusinessError


@dataclass(frozen=True)
class RequestIdentity:
    """Trusted principal supplied by the Next.js BFF for any business module."""
    kind: Literal['user', 'anonymous']
    subject_id: str


@dataclass(frozen=True)
class MigrationIdentity:
    """Trusted target account and source browser identity for Chat claim only."""
    target_owner: str
    source_owner: str


def require_bff(request: Request) -> None:
    secret = os.getenv('BACKEND_BFF_SECRET', '')
    if secret:
        if secrets.compare_digest(request.headers.get('x-shenzhi-bff-secret', ''), secret):
            return
        raise BusinessError(10001, '无效的后端调用凭据', 401)

    allow_local = os.getenv('BACKEND_ALLOW_INSECURE_LOCAL_BFF', '').strip().lower() == 'true'
    host = request.client.host if request.client else ''
    try:
        is_loopback = ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not allow_local or not is_loopback:
        raise BusinessError(10001, '后端调用凭据未配置', 503)


def request_identity(request: Request) -> RequestIdentity:
    require_bff(request)
    user_id = request.headers.get('x-shenzhi-user-id')
    anonymous_id = request.headers.get('x-shenzhi-anonymous-id')
    if (user_id is None) == (anonymous_id is None):
        raise BusinessError(10001, '请通过 Web 入口访问业务服务', 401)
    if user_id is not None:
        if not _valid_user_id(user_id):
            raise BusinessError(10001, '请通过 Web 入口访问业务服务', 401)
        return RequestIdentity(kind='user', subject_id=user_id)
    try:
        return RequestIdentity(kind='anonymous', subject_id=str(UUID(anonymous_id or '')))
    except ValueError:
        raise BusinessError(10001, '请通过 Web 入口访问会话', 401) from None


def require_user(request: Request) -> RequestIdentity:
    """Require an authenticated Better Auth identity for user-owned data."""
    identity = request_identity(request)
    if identity.kind != 'user':
        raise BusinessError(10001, '请登录后使用此功能', 401)
    return identity


def request_owner(request: Request) -> str:
    """Chat compatibility adapter; other modules may depend on request_identity directly."""
    identity = request_identity(request)
    prefix = 'user' if identity.kind == 'user' else 'anon'
    return f'{prefix}:{identity.subject_id}'


def migration_identity(request: Request) -> MigrationIdentity:
    """Parse the dedicated dual-identity contract without weakening normal requests."""
    require_bff(request)
    user_id = request.headers.get('x-shenzhi-user-id')
    anonymous_id = request.headers.get('x-shenzhi-source-anonymous-id')
    if user_id is None or anonymous_id is None or not _valid_user_id(user_id):
        raise BusinessError(10001, '请通过 Web 登录后认领匿名会话', 401)
    try:
        source_id = str(UUID(anonymous_id))
    except ValueError:
        raise BusinessError(10001, '无效的匿名会话来源', 401) from None
    return MigrationIdentity(
        target_owner=f'user:{user_id}',
        source_owner=f'anon:{source_id}',
    )


def _valid_user_id(value: str) -> bool:
    return 0 < len(value) <= 255 and value == value.strip() and all(ord(char) >= 32 and ord(char) != 127 for char in value)
