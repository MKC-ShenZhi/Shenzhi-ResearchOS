"""抓取单个 URL 的正文（移植 SZDR `src/tools/fetch-url.tool.ts`）。

与 `read_paper` 的分工：这是**通用网页正文**通道（官方文档、博客、项目页、公告），
`read_paper` 专走 PDF 全文。两者共用 `integrations.public_web.security` 的出网安全网关
（逐跳 SSRF 校验 + 字节上限）。
"""
from __future__ import annotations

import asyncio
import json

import httpx
from pydantic import BaseModel

from agent_app.errors import BusinessError
from agent_app.integrations.public_web.fetch import fetch_public
from agent_app.integrations.public_web.security import BlockedUrlError
from agent_app.capabilities.html import html_text
from agent_app.execution.tools import Tool, ToolOutput, tool

MAX_BYTES = 6_000_000
MAX_TEXT_CHARS = 7000
TIMEOUT_S = 60.0
_UA = {'user-agent': 'ShenZhiResearchOS/1.0 (+research assistant)'}


class FetchUrlArgs(BaseModel):
    url: str
    max_chars: int | None = None


def fetch_url_tool(*, transport: httpx.BaseTransport | None = None) -> Tool:

    @tool(name='fetch_url',
          description='抓取一个公开网页并返回其正文文本（已去掉脚本/样式/导航）。',
          params=FetchUrlArgs, timeout_s=90.0,
          snippet='抓取单个网页并返回正文文本')
    async def fetch_url(args: FetchUrlArgs) -> str | ToolOutput:
        max_chars = max(500, min(args.max_chars or MAX_TEXT_CHARS, MAX_TEXT_CHARS))
        return await asyncio.to_thread(_fetch_url_sync, args, max_chars, transport)

    return fetch_url


def _fetch_url_sync(args: FetchUrlArgs, max_chars: int,
                    transport: httpx.BaseTransport | None) -> str:
    """Fetch through the bounded public-web integration; parse in the capability layer."""
    try:
        response = fetch_public(args.url, timeout=TIMEOUT_S, max_bytes=MAX_BYTES,
                                headers=_UA, transport=transport)
    except BlockedUrlError as exc:
        raise BusinessError(20004, str(exc)) from exc
    except ValueError as exc:
        raise BusinessError(20004, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise BusinessError(20004, f'抓取失败：{exc}') from exc
    if response.status_code >= 400:
        raise BusinessError(20004, f'目标返回 HTTP {response.status_code}')
    content_type = response.headers.get('content-type', '')
    raw = response.content
    text = html_text(raw) if ('html' in content_type or not content_type) else \
        raw.decode('utf-8', 'replace')
    if not text.strip():
        raise BusinessError(20004, '页面没有可提取的正文（可能是纯前端渲染或空页）')
    clipped = text[:max_chars]
    payload = {
        'url': response.url,
        'content_type': content_type or 'unknown',
        'text_chars': len(clipped),
        'truncated': bool(len(text) > max_chars),
        'text': clipped,
    }
    return json.dumps(payload, ensure_ascii=False)
