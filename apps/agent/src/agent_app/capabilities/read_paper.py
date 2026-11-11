"""读全文：把一个 PDF（分页文本）或网页正文读进来。

移植 SZDR `src/tools/read-paper.tool.ts` 的语义，按本基座的能力裁剪：

- 先找可达的 PDF（给定 URL → 知识库详情里的 pdf_url → arXiv abs/pdf 互换 → DOI→Unpaywall），
  逐页抽取文本并**保留页号**（细节论断要能标到页）；
- 所有 PDF 候选都失败才退回读该页 HTML，并显式标 `pdf: false`——网页正文是**页面级**证据，
  不是全文级，模型据此决定能支撑什么；
- 每一次文本缩减都带显式标记（`truncated` / `text_chars` / `total_chars`），
  模型永远知道"自己实际读到了多少"，不会把被截断的头部当全文。

不做（SZDR 有而我们没有，明确记录）：PDF 首页转 PNG + 视觉核验（需要渲染与视觉模型）、
图片资产落盘。少了视觉通道意味着**图/表中的数字读不到**，这属于覆盖缺口，必须在报告里申报。
"""
from __future__ import annotations

import asyncio
import io
import json
from typing import Any

import httpx
from pydantic import BaseModel

from agent_app.errors import BusinessError
from agent_app.integrations.paper_resource.agent_sources import pdf_candidates, unpaywall_pdf
from agent_app.integrations.public_web.fetch import fetch_public
from agent_app.integrations.public_web.security import BlockedUrlError, looks_like_pdf
from agent_app.capabilities.html import html_text

_html_text = html_text  # compatibility for prior capability callers
from agent_app.execution.tools import Tool, ToolOutput, tool

MAX_PDF_BYTES = 90_000_000
# 单次全文返回上限。**刻意不用 ×3**：单条结果越大，越容易撞上下文预算
# （实测每篇 18 万字符 × 几篇就直接溢出），需要更多时让模型翻页重取。
DEFAULT_TEXT_CHARS = 7000
MAX_TEXT_CHARS = 7000
MAX_HTML_BYTES = 6_000_000
REQUEST_TIMEOUT_S = 60.0
_UA = {'user-agent': 'ShenZhiResearchOS/1.0 (+research assistant)'}


class ReadPaperArgs(BaseModel):
    # url 与 paper_id 至少给一个：给 paper_id 时经知识库详情拿 pdf_url（比猜 arXiv 路径可靠）
    url: str | None = None
    paper_id: str | None = None
    page_from: int | None = None      # 从第几页开始（1-based）
    page_to: int | None = None        # 读到第几页（含）
    max_chars: int | None = None      # 单次约 7000 字符，读实验/结果章节请用 page_from/page_to 定位


def _pdf_pages(data: bytes) -> tuple[str, list[str], int]:
    """抽取 PDF 文本：返回 (标题, 每页文本, 总页数)。"""
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — 任何解析失败都按"这篇读不到"处理
        raise ValueError(f'PDF 解析失败: {exc}') from exc
    title = ''
    try:
        meta = reader.metadata or {}
        title = str(meta.get('/Title') or '').strip()
    except Exception:  # noqa: BLE001
        title = ''
    pages = [page.extract_text() or '' for page in reader.pages]
    return title, pages, len(pages)


def _paginate(pages: list[str], page_from: int | None, page_to: int | None,
              max_chars: int) -> tuple[str, dict[str, Any]]:
    """按页号切片并做字符上限；每个缩减都如实标记。"""
    total = len(pages)
    start = max(1, page_from or 1)
    end = min(total, page_to or total)
    if start > total:
        raise BusinessError(20004, f'page_from={start} 超出总页数 {total}')
    selected = list(enumerate(pages[start - 1:end], start))
    parts: list[str] = []
    used = 0
    cut_page: int | None = None
    read_to = start - 1
    for page_no, text in selected:
        body = (text or '').strip()
        if not body:
            continue
        block = f'--- p.{page_no} ---\n{body}'
        separator_chars = 2 if parts else 0
        remain = max_chars - used - separator_chars
        if len(block) > remain:
            cut_page = page_no
            if remain > 200:
                parts.append(block[:remain])
                read_to = page_no
            break
        parts.append(block)
        used += separator_chars + len(block)
        read_to = page_no
    text = '\n\n'.join(parts)
    meta: dict[str, Any] = {
        'pages_total': total,
        'pages_read': f'{start}-{read_to}',
        'text_chars': len(text),
    }
    if cut_page is not None:
        meta['truncated'] = {'by': 'max_chars', 'at_page': cut_page, 'limit': max_chars}
        meta['next_page_from'] = cut_page
    return text, meta


def read_paper_tool(*, knowledge: Any = None, transport: httpx.BaseTransport | None = None) -> Tool:
    """工厂：knowledge 提供"按 paper_id 取 pdf_url"（缺省不启用该候选）。"""

    @tool(name='read_paper',
          description='读取一个 URL 或论文的 PDF 全文，返回带页号的文本；无 PDF 可达时'
                      '退回抓取该页正文（此时 pdf=false）。'
                      '单次约 7000 字符，读实验/结果章节请用 page_from/page_to 定位。',
          params=ReadPaperArgs, timeout_s=120.0,
          snippet='读 PDF 全文（带页号）或退回网页正文')
    async def read_paper(args: ReadPaperArgs) -> str | ToolOutput:
        target = (args.url or '').strip()
        paper_id = (args.paper_id or '').strip()
        if not target and not paper_id:
            raise BusinessError(20001, 'read_paper 需要 url 或 paper_id 之一')
        requested_chars = args.max_chars if args.max_chars is not None else DEFAULT_TEXT_CHARS
        max_chars = max(200, min(requested_chars, MAX_TEXT_CHARS))
        # paper_id 优先走知识库的 pdf_url；异步知识库调用保留在事件循环中。
        resolved = await _resolve_pdf_url(knowledge, paper_id or target)
        return await asyncio.to_thread(_read_paper_sync, args, target, resolved,
                                       max_chars, transport)

    return read_paper


def _read_paper_sync(args: ReadPaperArgs, target: str, resolved: str | None,
                    max_chars: int, transport: httpx.BaseTransport | None) -> str:
    """Download through the public-web integration and parse in this capability."""
    paper_id = (args.paper_id or '').strip()
    if not target and resolved is None:
        raise BusinessError(20004, f'知识库没有 {paper_id} 的可达 PDF 地址'
                                   f'（可改用 paper_detail 看摘要，或用 URL 重试）')
    candidates = pdf_candidates(target or resolved or '')
    if resolved:
        candidates.insert(0, resolved)
    failures: list[str] = []
    for candidate in candidates:
        try:
            response = fetch_public(candidate, timeout=REQUEST_TIMEOUT_S,
                                    max_bytes=MAX_PDF_BYTES, headers=_UA, transport=transport)
            if response.status_code >= 400:
                failures.append(f'{candidate}: HTTP {response.status_code}')
                continue
            content_type = response.headers.get('content-type', '')
            if not looks_like_pdf(candidate, content_type):
                if 'json' in content_type:
                    best = unpaywall_pdf(response.json())
                    if best:
                        candidates.append(best)
                        continue
                page_text = html_text(response.content[:MAX_HTML_BYTES])
                if page_text:
                    return json.dumps(_html_payload(candidate, page_text, max_chars,
                                                    failures), ensure_ascii=False)
                failures.append(f'{candidate}: 页面无可提取正文')
                continue
            title, pages, _total = _pdf_pages(response.content)
            text, meta = _paginate(pages, args.page_from, args.page_to, max_chars)
            if not text.strip():
                failures.append(f'{candidate}: PDF 无可用文本层（可能是扫描件）')
                continue
            payload = {'title': title or candidate, 'url': candidate, 'pdf': True,
                       **meta, 'text': text}
            return json.dumps(payload, ensure_ascii=False)
        except (BlockedUrlError, ValueError, httpx.HTTPError) as exc:
            failures.append(f'{candidate}: {exc}')
    try:
        fallback = target or resolved or ''
        response = fetch_public(fallback, timeout=REQUEST_TIMEOUT_S,
                                max_bytes=MAX_HTML_BYTES, headers=_UA, transport=transport)
        if response.status_code >= 400:
            raise BusinessError(20004, f'网页返回 HTTP {response.status_code}')
        text = html_text(response.content)
        if not text:
            raise BusinessError(20004, '网页没有可提取的正文')
        return json.dumps(_html_payload(fallback, text, max_chars, failures),
                          ensure_ascii=False)
    except BusinessError as exc:
        detail = '; '.join(failures[:3]) or '无 PDF 候选'
        raise BusinessError(20004,
                            f'无法读取 {target}: {exc.message}（PDF 尝试：{detail}）') from exc
    except (BlockedUrlError, ValueError, httpx.HTTPError) as exc:
        detail = '; '.join(failures[:3]) or '无 PDF 候选'
        raise BusinessError(20004, f'无法读取 {target}: {exc}（PDF 尝试：{detail}）') from exc


def _html_payload(url: str, text: str, max_chars: int, failures: list[str]) -> dict[str, Any]:
    """网页正文制品：显式 pdf=false，说明这是页面级证据而非全文。"""
    clipped = text[:max_chars]
    return {
        'title': url, 'url': url, 'pdf': False,
        'text_chars': len(clipped),
        'truncated': {'by': 'max_chars', 'limit': max_chars} if len(text) > max_chars else None,
        'pdf_failures': failures[:4],
        'text': clipped,
    }


async def _resolve_pdf_url(knowledge: Any, paper_id: str) -> str | None:
    """若知识库能按 opaque paper_id 给出 pdf_url，优先使用且不得改写 ID。"""
    if knowledge is None or not paper_id:
        return None
    exact_id = paper_id.strip()
    if not exact_id.startswith('paper:'):
        return None
    detail = await knowledge.get_paper(exact_id)
    return getattr(detail, 'pdf_url', None) or None


_unpaywall_pdf = unpaywall_pdf  # compatibility for existing callers/tests

