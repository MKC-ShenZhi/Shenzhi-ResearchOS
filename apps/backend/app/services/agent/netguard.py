"""出网抓取的安全网关（移植 SZDR `src/services/fetch/url-guard.ts`）。

用户、模型、以及被抓回的页面都可能给出 URL，因此 agent 能被人说服去请求的任何地址都要经过这里，
使它无法触达 loopback、私网与云元数据端点（SSRF）。

残留风险（与 SZDR 原文一致，明确记录而非假装没有）：地址在请求前与每个重定向跳点都校验过，
但真正的连接会再解析一次主机名；两次解析之间发生 DNS rebinding 的名字仍可能穿过。要彻底关掉这个
窗口需要 pinned-connection dispatcher，不值得为此引入依赖。
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

BLOCKED_HOSTNAMES = frozenset({
    'localhost', 'metadata', 'metadata.google.internal', 'metadata.goog', 'instance-data',
})

# 绝不允许 agent 发起的抓取触达的 IPv4 段（CIDR 形式，含云元数据 169.254.169.254）
BLOCKED_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in (
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16',
    '172.16.0.0/12', '192.0.0.0/24', '192.168.0.0/16', '198.18.0.0/15',
    '224.0.0.0/4', '240.0.0.0/4',
    # IPv6：未指定/回环/唯一本地/链路本地/组播/NAT64 well-known/文档段
    '::/128', '::1/128', 'fc00::/7', 'fe80::/10', 'ff00::/8', '64:ff9b::/96',
    '2001:db8::/32',
))

_DOTTED_V4 = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$')


class BlockedUrlError(Exception):
    """目标地址被安全策略拒绝（本地/私网/保留地址或非 HTTP(S)）。"""


def is_blocked_address(address: str) -> bool:
    """判断一个字面 IP 是否落在禁止段内；无法解析的地址一律视为禁止（fail closed）。"""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return True
    # IPv4-mapped / 6to4 等形式携带内嵌 IPv4：先按内嵌地址判定
    if isinstance(parsed, ipaddress.IPv6Address):
        mapped = parsed.ipv4_mapped or parsed.sixtofour
        if mapped is not None:
            return is_blocked_address(str(mapped))
    return any(parsed in network for network in BLOCKED_NETWORKS)


def _assert_public_hostname(hostname: str) -> None:
    name = hostname.lower().rstrip('.')
    if name in BLOCKED_HOSTNAMES or name.endswith('.localhost') or name.endswith('.internal'):
        raise BlockedUrlError(f'拒绝抓取本地或内部主机: {hostname}')


def assert_public_http_url(raw: str) -> httpx.URL:
    """校验协议与主机，并校验主机名解析出的**每一个**地址。"""
    try:
        url = httpx.URL(raw)
    except (httpx.InvalidURL, ValueError) as exc:
        raise BlockedUrlError(f'不是合法 URL: {raw}') from exc
    if url.scheme not in ('http', 'https'):
        raise BlockedUrlError(f'只允许 HTTP(S) URL，收到 {url.scheme}: {raw}')
    hostname = url.host or ''
    _assert_public_hostname(hostname)

    literal = hostname.strip('[]')
    if _DOTTED_V4.search(literal) or ':' in literal:
        if is_blocked_address(literal):
            raise BlockedUrlError(f'拒绝抓取私有或保留地址: {hostname}')
        return url

    try:
        resolved = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise BlockedUrlError(f'无法解析主机 {hostname}: {exc}') from exc
    addresses = {info[4][0] for info in resolved}
    if not addresses:
        raise BlockedUrlError(f'主机 {hostname} 没有解析出任何地址')
    for address in addresses:
        if is_blocked_address(address):
            raise BlockedUrlError(f'拒绝抓取 {hostname}：它解析到私有地址 {address}')
    return url


def safe_get(client: httpx.Client, raw: str, *, max_redirects: int = 4) -> httpx.Response:
    """带逐跳校验的 GET（重定向手动跟随，每一跳都重新校验）。"""
    target = assert_public_http_url(raw)
    visited = {str(target)}
    for hop in range(max_redirects + 1):
        response = client.get(target, follow_redirects=False)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get('location')
        if not location:
            return response
        if hop >= max_redirects:
            raise BlockedUrlError(f'重定向次数过多: {raw}')
        next_url = urljoin(str(target), location)
        if next_url in visited:
            raise BlockedUrlError(f'重定向成环: {raw}')
        visited.add(next_url)
        target = assert_public_http_url(next_url)
    raise BlockedUrlError(f'重定向次数过多: {raw}')


def read_bytes_capped(response: httpx.Response, max_bytes: int) -> bytes:
    """带硬上限地读取响应体：恶意或过大的响应不能耗尽内存。"""
    declared = int(response.headers.get('content-length') or 0)
    if declared > max_bytes:
        raise ValueError(f'响应声明 {declared} 字节，超过 {max_bytes} 上限')
    parts: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > max_bytes:
            raise ValueError(f'响应体超过 {max_bytes} 字节上限')
        parts.append(chunk)
    return b''.join(parts)


def looks_like_pdf(url: str, content_type: str) -> bool:
    return url.lower().split('?')[0].endswith('.pdf') or 'pdf' in content_type.lower()
