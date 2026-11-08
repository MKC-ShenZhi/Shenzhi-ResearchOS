"""Exa image search transport and response normalization."""
from __future__ import annotations

from typing import Any
import os

import httpx

EXA_ENDPOINT = 'https://api.exa.ai/search'
TIMEOUT_S = 45.0


class ExaImageSearchError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _images(body: Any) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for item in (body or {}).get('results') or []:
        if not isinstance(item, dict):
            continue
        candidates = [*(item.get('richImageLinks') or []), *(item.get('imageLinks') or []),
                      *((item.get('extras') or {}).get('richImageLinks') or [])]
        for entry in candidates:
            url = entry.get('url') if isinstance(entry, dict) else None
            if isinstance(url, str) and url.startswith(('http://', 'https://')):
                images.append({'title': str(item.get('title') or '').strip(),
                               'imageUrl': url, 'sourceUrl': str(item.get('url') or '')})
    return images


async def search_images(query: str, limit: int, *, transport: httpx.AsyncBaseTransport | None = None) -> list[dict[str, str]]:
    api_key = os.getenv('EXA_API_KEY', '').strip()
    if not api_key:
        raise ExaImageSearchError('图片检索未配置（EXA_API_KEY）')
    payload = {'query': query, 'type': 'neural', 'numResults': limit,
               'contents': {'richImageLinks': True}}
    async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
        try:
            response = await client.post(EXA_ENDPOINT, json=payload,
                                         headers={'content-type': 'application/json', 'x-api-key': api_key})
        except httpx.HTTPError as exc:
            raise ExaImageSearchError(f'图片检索失败：{exc}') from exc
        if response.status_code >= 400:
            raise ExaImageSearchError(f'图片检索失败（Exa {response.status_code}）：{response.text[:200]}',
                                      status_code=response.status_code)
        try:
            return _images(response.json())
        except (ValueError, AttributeError) as exc:
            raise ExaImageSearchError('图片检索失败：Exa 返回格式无效') from exc


IMAGE_EXTENSIONS = {'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/gif':'gif'}

def fetch_image(url: str, *, max_bytes: int, transport: httpx.BaseTransport | None = None) -> tuple[bytes, str] | None:
    """Fetch one public image with redirect checks, byte cap and content-type validation."""
    from app.integrations.public_web.security import BlockedUrlError, read_bytes_capped, safe_get
    try:
        with httpx.Client(timeout=TIMEOUT_S,follow_redirects=False,transport=transport) as client:
            response=safe_get(client,url)
            if response.status_code >= 400: return None
            content_type=response.headers.get('content-type','').split(';')[0].strip().lower()
            extension=IMAGE_EXTENSIONS.get(content_type)
            if extension is None: return None
            data=read_bytes_capped(response,max_bytes)
            return (data,extension) if data else None
    except (BlockedUrlError,ValueError,httpx.HTTPError):
        return None
