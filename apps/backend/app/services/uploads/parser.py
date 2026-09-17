"""In-memory PDF/TXT/Markdown extraction."""
import io
import re
from pathlib import Path
from pypdf import PdfReader
from app.core.config import MAX_UPLOAD_BYTES, MAX_FILE_CHARS, UPLOAD_ACCEPT
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
