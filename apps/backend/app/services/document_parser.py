"""In-memory PDF/TXT/Markdown extraction with B's 30k/60k context limits."""
import io
import json
import re
from pathlib import Path
from pypdf import PdfReader
from app.core.config import MAX_UPLOAD_BYTES, MAX_FILE_CHARS, MAX_ATTACHMENT_CHARS, UPLOAD_ACCEPT
from app.core.errors import BusinessError


def parse_document(data: bytes, filename: str) -> dict:
    if len(data) > MAX_UPLOAD_BYTES:
        raise BusinessError(20006, '附件不能超过 20MB', 413)
    ext = Path(filename).suffix.lower()
    if ext not in UPLOAD_ACCEPT:
        raise BusinessError(20006, '仅支持 PDF、TXT、Markdown 附件', 415)
    try:
        if ext == '.pdf':
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('encrypted PDF')
            raw = '\n'.join(page.extract_text() or '' for page in reader.pages)
        else:
            raw = data.decode('utf-8-sig')
    except Exception as exc:
        raise BusinessError(20006, '附件解析失败，请上传未加密文字版 PDF 或 UTF-8 文本', 422) from exc
    normalized = re.sub(r'\n{3,}', '\n\n', raw.replace('\r\n', '\n')).strip()
    if not normalized:
        raise BusinessError(20006, '提取文本为空；暂不支持扫描 PDF / OCR', 422)
    truncated = len(normalized) > MAX_FILE_CHARS
    return {'text': normalized[:MAX_FILE_CHARS], 'original_length': len(normalized),
            'final_length': min(len(normalized), MAX_FILE_CHARS), 'truncated': truncated,
            'warning': f'附件「{filename}」已截断至前 30,000 字' if truncated else None}


def attachment_context(attachments, owner: str, repository, paper_contexts: dict[str, str] | None = None) -> tuple[str, list[str]]:
    parts, warnings = [], []
    remaining = MAX_ATTACHMENT_CHARS
    for attachment in attachments:
        if attachment.kind == 'file':
            item = repository.upload(attachment.file_id or '', owner)
            text = item['text']
            if item['warning']:
                warnings.append(item['warning'])
            label = item['filename']
        elif attachment.kind == 'paper':
            text = (paper_contexts or {}).get(attachment.ref_id or '')
            if text is None:
                raise BusinessError(20007, '当前论文上下文不可用，请重新加载论文后重试', 503)
            label = 'paper_metadata'
            warnings.append('本轮仅使用论文元信息与摘要，未读取 PDF 全文')
        else:
            # A's references remain selectable, but are NOT passed off as retrieved full texts.
            text = f'用户引用的条目：{attachment.title or attachment.ref_id or attachment.kind}（未接入全文解析）'
            label = attachment.kind
            warnings.append('知识库 / 项目引用目前仅提供条目名称，未读取全文')
        prefix = f'\n<attachment name={label!r}>\n'
        suffix = '\n</attachment>\n'
        block = prefix + text + suffix
        if attachment.kind == 'paper' and len(block) > remaining:
            raise BusinessError(20007, '论文上下文超过附件容量，请减少附件后重试', 422)
        if len(block) > remaining:
            warnings.append('多附件上下文已截断至合计 60,000 字')
        parts.append(block[:remaining])
        remaining = max(0, remaining - len(block))
    return ''.join(parts), list(dict.fromkeys(warnings))


def format_paper_context(paper) -> tuple[str, bool]:
    """Bounded server-resolved data; never interpolate external delimiters."""
    abstract = paper.abstract or ''
    data = {
        'paper_id': paper.id,
        'title': paper.title[:1000],
        'authors': [author[:200] for author in paper.authors[:50]],
        'venue': (paper.venue or '')[:500],
        'year': paper.year,
        'abstract': abstract[:20_000],
        'doi': (paper.doi or '')[:500],
        'citation_count': paper.citation_count,
        'reference_count': paper.reference_count,
    }
    # JSON escapes newlines/quotes; escape markup delimiters as literal data.
    text = json.dumps(data, ensure_ascii=False).replace('<', r'\u003c').replace('>', r'\u003e')
    return text, len(abstract) > 20_000
