import os
import time
import hmac
import hashlib
import secrets
from ipaddress import ip_address
from pathlib import Path
from fastapi import Request
from app.core.errors import BusinessError

COOKIE = 'shenzhi_admin_session'
PATH = '/api/v1/admin-console'


def tunnel_settings(request: Request):
    """Trust only a dedicated entry proxy carrying a server-side shared secret."""
    try:
        key = Path(os.environ['ADMIN_ENTRY_SECRET_FILE']).read_text(encoding='utf-8').strip()
        username = os.environ['ADMIN_TUNNEL_PRINCIPAL'].strip()
        session_secret = os.environ['ADMIN_SESSION_SECRET']
        ttl = int(os.getenv('ADMIN_SESSION_TTL_SECONDS', '28800'))
    except (KeyError, OSError, ValueError):
        raise BusinessError(10002, '隧道管理认证配置无效', 503) from None
    if (len(key) != 64 or any(char not in '0123456789abcdef' for char in key)
            or not username or len(username) > 100 or
            any(not (char.isascii() and (char.isalnum() or char in '_.@-')) for char in username)
            or len(session_secret) < 32 or key == session_secret or not 0 < ttl <= 86400):
        raise BusinessError(10002, '隧道管理认证配置无效', 503)
    hosts = os.getenv('ADMIN_TUNNEL_ALLOWED_HOSTS', '127.0.0.1:3101 localhost:3101').split()
    host = request.headers.get('host', '')
    origin = request.headers.get('origin')
    if (host not in hosts or request.headers.get('sec-fetch-site') == 'cross-site'
            or (origin and origin not in ('http://' + host, 'https://' + host))
            or not hmac.compare_digest(request.headers.get('x-shenzhi-admin-entry', '').encode(), key.encode())):
        raise BusinessError(10001, '管理入口校验失败', 403)
    return username, key, session_secret, ttl


def settings(request: Request):
    try:
        local = bool(request.client and ip_address(request.client.host).is_loopback)
    except ValueError:
        local = False
    # Never trust browser-supplied identity or forwarding headers here.
    if not local:
        raise BusinessError(10001, '本地管理员认证仅允许 loopback 访问', 403)
    if os.getenv('ADMIN_AUTH_MODE') == 'ssh_tunnel':
        return tunnel_settings(request)
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
            or (password == 'shenzhi-dev' and os.getenv('ENVIRONMENT') != 'development')
            or not 0 < ttl <= 86400):
        raise BusinessError(10002, '管理员认证配置缺失或无效', 503)
    return username, password, secret, ttl


def signature(payload, secret, username, password):
    # Credential rotation also invalidates existing sessions.
    key = hashlib.pbkdf2_hmac('sha256', (username + '\0' + password).encode(), secret.encode(), 120_000)
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def login(request, username, password):
    if os.getenv('ADMIN_AUTH_MODE') == 'ssh_tunnel':
        raise BusinessError(10001, '请通过 SSH 管理入口建立会话', 403)
    configured_user, configured_password, secret, ttl = settings(request)
    valid_user = secrets.compare_digest(username.encode(), configured_user.encode())
    valid_password = secrets.compare_digest(password.encode(), configured_password.encode())
    if not (valid_user & valid_password):
        raise BusinessError(10001, '账号或密码错误', 401)
    payload = f'{int(time.time())}.{secrets.token_hex(16)}'
    return payload + '.' + signature(payload, secret, configured_user, configured_password), ttl


def tunnel_session(request):
    username, key, secret, ttl = settings(request)
    payload = f'{int(time.time())}.{secrets.token_hex(16)}'
    return username, payload + '.' + signature(payload, secret, username, key), ttl


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


def require_admin_write(request: Request):
    username = require_admin(request)
    # Non-simple same-origin request: cross-origin browsers require a CORS
    # preflight, which this application does not grant. Cookie alone is insufficient.
    if request.headers.get('x-admin-request') != '1' or request.headers.get('sec-fetch-site') == 'cross-site':
        raise BusinessError(10001, '管理员写操作必须通过同源控制台提交', 403)
    return ('ssh-admin:' if os.getenv('ADMIN_AUTH_MODE') == 'ssh_tunnel' else 'local-admin:') + username
