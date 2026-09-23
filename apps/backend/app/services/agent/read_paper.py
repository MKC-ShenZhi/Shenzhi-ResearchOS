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

import io
import re
from typing import Any
from urllib.parse import quote

import httpx
import lxml.html
from pydantic import BaseModel

from app.core.errors import BusinessError
from app.services.agent.netguard import (
    BlockedUrlError, looks_like_pdf, read_bytes_capped, safe_get,
)
from app.services.agent.tools import Tool, ToolOutput, tool

MAX_PDF_BYTES = 90_000_000
# 单次全文返回上限。**刻意不用 ×3**：单条结果越大，越容易撞上下文预算
# （实测每篇 18 万字符 × 几篇就直接溢出），需要更多时让模型翻页重取。
MAX_TEXT_CHARS = 60_000
MAX_HTML_BYTES = 6_000_000
REQUEST_TIMEOUT_S = 60.0
_UA = {'user-agent': 'ShenZhiResearchOS/1.0 (+research assistant)'}
_STRIP_TAGS = ('script', 'style', 'noscript', 'nav', 'footer', 'header', 'form', 'svg')


class ReadPaperArgs(BaseModel):
    # url 与 paper_id 至少给一个：给 paper_id 时经知识库详情拿 pdf_url（比猜 arXiv 路径可靠）
    url: str | None = None
    paper_id: str | None = None
    page_from: int | None = None      # 从第几页开始（1-based）
    page_to: int | None = None        # 读到第几页（含）
    max_chars: int | None = None      # 文本上限，缺省 60000


def pdf_candidates(url: str) -> list[str]:
    """从给定 URL 推导可达的 PDF 候选（SZDR pdfCandidates 的等价实现）。

    arXiv 的 abs 页与 pdf 页互换、OpenReview 的 forum 页换 pdf、DOI 走 Unpaywall。
    DOI→Unpaywall 需要邮箱参数，因此只在 DOI 出现时使用；失败不影响其他候选。
    """
    url = url.strip()
    out = [url]
    arxiv = re.search(r'arxiv\.org/(abs|pdf)/([0-9]+\.[0-9]+)', url)
    if arxiv:
        ident = arxiv.group(2)
        out += [f'https://arxiv.org/pdf/{ident}', f'https://arxiv.org/abs/{ident}']
    openreview = re.search(r'openreview\.net/forum\?id=([\w-]+)', url)
    if openreview:
        out.append(f"https://openreview.net/pdf?id={openreview.group(1)}")
    doi = re.search(r'doi\.org/(10\.[^\s?#]+)', url)
    if doi:
        out.append(f'https://api.unpaywall.org/v2/{quote(doi.group(1), safe="")}?email=research@example.org')
    seen: set[str] = set()
    return [item for item in out if not (item in seen or seen.add(item))]


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


def _html_text(raw: bytes) -> str:
    """网页正文：去脚本样式与导航，取可见文本并压空白。"""
    try:
        document = lxml.html.fromstring(raw)
    except Exception:  # noqa: BLE001
        return ''
    for tag in document.iter(*_STRIP_TAGS):
        tag.drop_tree()
    text = document.text_content()
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()


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
    for page_no, text in selected:
        body = (text or '').strip()
        if not body:
            continue
        block = f'--- p.{page_no} ---\n{body}'
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain > 200:
                parts.append(block[:remain])
                cut_page = page_no
            break
        parts.append(block)
        used += len(block)
    text = '\n\n'.join(parts)
    meta: dict[str, Any] = {
        'pages_total': total,
        'pages_read': f'{start}-{end}',
        'text_chars': len(text),
    }
    if cut_page is not None or used < sum(len((p or '').strip()) for _, p in selected):
        meta['truncated'] = {'by': 'max_chars', 'at_page': cut_page, 'limit': max_chars}
    return text, meta


def read_paper_tool(*, knowledge: Any = None, transport: httpx.BaseTransport | None = None) -> Tool:
    """工厂：knowledge 提供"按 paper_id 取 pdf_url"（缺省不启用该候选）。"""

    @tool(name='read_paper',
          description='读取一个 URL 或论文的 PDF 全文，返回带页号的文本；无 PDF 可达时'
                      '退回抓取该页正文（此时 pdf=false）。',
          params=ReadPaperArgs, timeout_s=120.0,
          snippet='读 PDF 全文（带页号）或退回网页正文')
    async def read_paper(args: ReadPaperArgs) -> str | ToolOutput:
        import json

        target = (args.url or '').strip()
        paper_id = (args.paper_id or '').strip()
        if not target and not paper_id:
            raise BusinessError(20001, 'read_paper 需要 url 或 paper_id 之一')
        max_chars = max(200, min(args.max_chars or MAX_TEXT_CHARS, MAX_TEXT_CHARS))
        with httpx.Client(timeout=REQUEST_TIMEOUT_S, headers=_UA, follow_redirects=False,
                          transport=transport) as client:
            # paper_id 优先走知识库的 pdf_url（最可靠）；拿不到再退回 URL/猜测路径
            resolved = await _resolve_pdf_url(knowledge, paper_id or target)
            if not target and resolved is None:
                raise BusinessError(20004, f'知识库没有 {paper_id} 的可达 PDF 地址'
                                           f'（可改用 paper_detail 看摘要，或用 URL 重试）')
            candidates = pdf_candidates(target or resolved or '')
            if resolved:
                candidates.insert(0, resolved)
            failures: list[str] = []
            for candidate in candidates:
                try:
                    response = safe_get(client, candidate)
                    if response.status_code >= 400:
                        failures.append(f'{candidate}: HTTP {response.status_code}')
                        continue
                    content_type = response.headers.get('content-type', '')
                    if not looks_like_pdf(candidate, content_type):
                        # Unpaywall 之类的 JSON 跳板：从里面再取一个 PDF 地址
                        if 'json' in content_type:
                            best = _unpaywall_pdf(response.json())
                            if best:
                                candidates.append(best)
                                continue
                        # 已经是网页正文：不必等候选耗尽，也不该把它记成"PDF 候选失败"重打一次
                        page_text = _html_text(read_bytes_capped(response, MAX_HTML_BYTES))
                        if page_text:
                            return json.dumps(_html_payload(candidate, page_text, max_chars,
                                                            failures), ensure_ascii=False)
                        failures.append(f'{candidate}: 页面无可提取正文')
                        continue
                    data = read_bytes_capped(response, MAX_PDF_BYTES)
                    title, pages, total = _pdf_pages(data)
                    text, meta = _paginate(pages, args.page_from, args.page_to, max_chars)
                    if not text.strip():
                        failures.append(f'{candidate}: PDF 无可用文本层（可能是扫描件）')
                        continue
                    payload = {'title': title or candidate, 'url': candidate, 'pdf': True,
                               **meta, 'text': text}
                    return json.dumps(payload, ensure_ascii=False)
                except (BlockedUrlError, ValueError, httpx.HTTPError) as exc:
                    failures.append(f'{candidate}: {exc}')
            # 所有 PDF 候选都失败 → 退回读网页正文，并如实标记 pdf=false
            try:
                response = safe_get(client, target or resolved or '')
                if response.status_code >= 400:
                    raise BusinessError(20004, f'网页返回 HTTP {response.status_code}')
                text = _html_text(read_bytes_capped(response, MAX_HTML_BYTES))
                if not text:
                    raise BusinessError(20004, '网页没有可提取的正文')
                return json.dumps(_html_payload(target, text, max_chars, failures),
                                  ensure_ascii=False)
            except BusinessError as exc:
                detail = '; '.join(failures[:3]) or '无 PDF 候选'
                raise BusinessError(20004,
                                    f'无法读取 {target}: {exc.message}（PDF 尝试：{detail}）') from exc
            except (BlockedUrlError, ValueError, httpx.HTTPError) as exc:
                detail = '; '.join(failures[:3]) or '无 PDF 候选'
                raise BusinessError(20004, f'无法读取 {target}: {exc}（PDF 尝试：{detail}）') from exc

    return read_paper


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


def _unpaywall_pdf(body: Any) -> str | None:
    """从 Unpaywall 响应里取最佳开放获取 PDF 地址。"""
    if not isinstance(body, dict):
        return None
    best = body.get('best_oa_location')
    if isinstance(best, dict) and isinstance(best.get('url_for_pdf'), str):
        return best['url_for_pdf']
    for location in body.get('oa_locations') or []:
        if isinstance(location, dict) and isinstance(location.get('url_for_pdf'), str):
            return location['url_for_pdf']
    return None
