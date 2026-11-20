import os
import time
import hmac
import hashlib
import secrets
from ipaddress import ip_address
from fastapi import Request
from app.core.errors import BusinessError

COOKIE = 'shenzhi_admin_session'
PATH = '/api/v1/admin-console'


def settings(request: Request):
    try:
        local = bool(request.client and ip_address(request.client.host).is_loopback)
    except ValueError:
        local = False
    # Never trust browser-supplied identity or forwarding headers here.
    if not local:
        raise BusinessError(10001, '本地管理员认证仅允许 loopback 访问', 403)
    username = os.getenv('ADMIN_LOCAL_USERNAME', '')
    password = os.getenv('ADMIN_LOCAL_PASSWORD', '')
    secret = os.getenv('ADMIN_SESSION_SECRET', '')
    try:
        ttl = int(os.getenv('ADMIN_SESSION_TTL_SECONDS', '28800'))
    except ValueError:
        ttl = 0
    if (os.getenv('ADMIN_AUTH_MODE') != 'local_password'
            or os.getenv('ADMIN_AUTH_LOCAL_ONLY', 'true').lower() != 'true'
            or not username or not password or password == 'CHANGE_ME' or len(secret) < 32
            or not 0 < ttl <= 86400):
        raise BusinessError(10002, '管理员认证配置缺失或无效', 503)
    return username, password, secret, ttl


def signature(payload, secret, username, password):
    # Credential rotation also invalidates existing sessions.
    key = hmac.digest(secret.encode(), (username + '\0' + password).encode(), 'sha256')
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def login(request, username, password):
    configured_user, configured_password, secret, ttl = settings(request)
    valid_user = secrets.compare_digest(username.encode(), configured_user.encode())
    valid_password = secrets.compare_digest(password.encode(), configured_password.encode())
    if not (valid_user & valid_password):
        raise BusinessError(10001, '账号或密码错误', 401)
    payload = f'{int(time.time())}.{secrets.token_hex(16)}'
    return payload + '.' + signature(payload, secret, configured_user, configured_password), ttl


def require_admin(request: Request):
    username, password, secret, ttl = settings(request)
    token = request.cookies.get(COOKIE, '')
    try:
        issued, nonce, supplied = token.split('.')
        payload = issued + '.' + nonce
        valid = secrets.compare_digest(supplied, signature(payload, secret, username, password))
        age = time.time() - int(issued)
        if not valid or not 0 <= age < ttl:
            raise ValueError()
    except (ValueError, TypeError):
        raise BusinessError(10001, '需要管理员登录', 401) from None
    return username
