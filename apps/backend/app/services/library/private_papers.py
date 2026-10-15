"""Authenticated storage for private library PDFs."""
from io import BytesIO
from pathlib import PurePath
import zlib

from pypdf import PdfReader
from sqlalchemy import delete, func, select, text
from starlette.concurrency import run_in_threadpool

from app.core.config import MAX_UPLOAD_BYTES
from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.collections import CollectionFolderRow
from app.models.private_paper import PrivatePaperRow

PRIVATE_PAPER_QUOTA_BYTES = 40 * 1024 * 1024
COMPRESSED_PREFIX = b'SZPDFZ1\0'


def _prepare_pdf(content: bytes) -> bytes:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or len(reader.pages) == 0:
            raise ValueError('encrypted or empty PDF')
    except Exception as exc:
        raise BusinessError(20006, 'PDF 无法读取或已加密', 422) from exc
    compressed = zlib.compress(content, level=6)
    # PDFs often contain compressed streams already. Avoid storing a larger blob.
    if len(compressed) + len(COMPRESSED_PREFIX) < len(content) * 0.95:
        return COMPRESSED_PREFIX + compressed
    return content


def _restore_pdf(stored: bytes, expected_size: int) -> bytes:
    if not stored.startswith(COMPRESSED_PREFIX):
        return stored
    inflater = zlib.decompressobj()
    try:
        content = inflater.decompress(stored[len(COMPRESSED_PREFIX):], MAX_UPLOAD_BYTES + 1)
        if (not inflater.eof or inflater.unused_data or len(content) != expected_size
                or not content.startswith(b'%PDF-')):
            raise ValueError('invalid compressed PDF')
        return content
    except zlib.error as exc:
        raise ValueError('invalid compressed PDF') from exc


def paper_summary(row: PrivatePaperRow) -> dict:
    return {'id': row.id, 'filename': row.filename, 'title': row.title,
            'size_bytes': row.size_bytes, 'created_at': row.created_at.isoformat()}


class PrivatePaperService:
    async def save(self, user_id: str, folder_id: int, filename: str, content: bytes) -> dict:
        filename = filename.replace('\\', '/').rsplit('/', 1)[-1].strip()[:255]
        if not filename.lower().endswith('.pdf') or not content.startswith(b'%PDF-'):
            raise BusinessError(20006, '仅支持 PDF 文件', 415)
        if len(content) > MAX_UPLOAD_BYTES:
            raise BusinessError(20006, '私有论文不能超过 20 MB', 413)
        stored = await run_in_threadpool(_prepare_pdf, content)
        async with session_scope() as session:
            # Serialize uploads for one user across backend instances before checking usage.
            await session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:user_id, 0))'),
                                  {'user_id': user_id})
            folder = await session.scalar(select(CollectionFolderRow.id).where(
                CollectionFolderRow.id == folder_id, CollectionFolderRow.user_id == user_id))
            if folder is None:
                raise BusinessError(40401, '文件夹不存在', 404)
            used = await session.scalar(select(func.coalesce(func.sum(PrivatePaperRow.size_bytes), 0)).where(
                PrivatePaperRow.user_id == user_id))
            if (used or 0) + len(content) > PRIVATE_PAPER_QUOTA_BYTES:
                raise BusinessError(20010, '私有论文总容量最多 40 MB，请删除部分论文后重试', 413)
            row = PrivatePaperRow(user_id=user_id, folder_id=folder_id, filename=filename,
                                  title=PurePath(filename).stem or '未命名论文',
                                  content=stored, size_bytes=len(content))
            session.add(row)
            await session.flush()
            return paper_summary(row)

    async def list(self, user_id: str, folder_id: int) -> list[dict]:
        async with session_scope() as session:
            folder = await session.scalar(select(CollectionFolderRow.id).where(
                CollectionFolderRow.id == folder_id, CollectionFolderRow.user_id == user_id))
            if folder is None:
                raise BusinessError(40401, '文件夹不存在', 404)
            rows = (await session.execute(select(
                PrivatePaperRow.id, PrivatePaperRow.filename, PrivatePaperRow.title,
                PrivatePaperRow.size_bytes, PrivatePaperRow.created_at,
            ).where(
                PrivatePaperRow.user_id == user_id, PrivatePaperRow.folder_id == folder_id)
                .order_by(PrivatePaperRow.created_at.desc(), PrivatePaperRow.id.desc()))).all()
            return [{'id': row.id, 'filename': row.filename, 'title': row.title,
                     'size_bytes': row.size_bytes, 'created_at': row.created_at.isoformat()}
                    for row in rows]

    async def file(self, user_id: str, paper_id: int) -> bytes:
        async with session_scope() as session:
            row = (await session.execute(select(PrivatePaperRow.content, PrivatePaperRow.size_bytes).where(
                PrivatePaperRow.id == paper_id, PrivatePaperRow.user_id == user_id))).one_or_none()
            if row is None:
                raise BusinessError(40401, '私有论文不存在', 404)
            stored, size_bytes = row
        try:
            return await run_in_threadpool(_restore_pdf, stored, size_bytes)
        except ValueError as exc:
            raise BusinessError(20004, '私有论文文件损坏，无法读取', 500) from exc

    async def delete(self, user_id: str, paper_id: int) -> None:
        async with session_scope() as session:
            result = await session.execute(delete(PrivatePaperRow).where(
                PrivatePaperRow.id == paper_id, PrivatePaperRow.user_id == user_id))
            if result.rowcount == 0:
                raise BusinessError(40401, '私有论文不存在', 404)
