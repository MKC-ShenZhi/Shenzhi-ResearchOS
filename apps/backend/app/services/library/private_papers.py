"""Authenticated storage for private library PDFs."""
from io import BytesIO
from pathlib import PurePath

from pypdf import PdfReader
from sqlalchemy import delete, select

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.collections import CollectionFolderRow
from app.models.private_paper import PrivatePaperRow


def paper_summary(row: PrivatePaperRow) -> dict:
    return {'id': row.id, 'filename': row.filename, 'title': row.title,
            'size_bytes': row.size_bytes, 'created_at': row.created_at.isoformat()}


class PrivatePaperService:
    async def save(self, user_id: str, folder_id: int, filename: str, content: bytes) -> dict:
        filename = filename.replace('\\', '/').rsplit('/', 1)[-1].strip()[:255]
        if not filename.lower().endswith('.pdf') or not content.startswith(b'%PDF-'):
            raise BusinessError(20006, '仅支持 PDF 文件', 415)
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted or len(reader.pages) == 0:
                raise ValueError('encrypted or empty PDF')
        except Exception as exc:
            raise BusinessError(20006, 'PDF 无法读取或已加密', 422) from exc
        async with session_scope() as session:
            folder = await session.scalar(select(CollectionFolderRow.id).where(
                CollectionFolderRow.id == folder_id, CollectionFolderRow.user_id == user_id))
            if folder is None:
                raise BusinessError(40401, '文件夹不存在', 404)
            row = PrivatePaperRow(user_id=user_id, folder_id=folder_id, filename=filename,
                                  title=PurePath(filename).stem or '未命名论文',
                                  content=content, size_bytes=len(content))
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
            content = await session.scalar(select(PrivatePaperRow.content).where(
                PrivatePaperRow.id == paper_id, PrivatePaperRow.user_id == user_id))
            if content is None:
                raise BusinessError(40401, '私有论文不存在', 404)
            return content

    async def delete(self, user_id: str, paper_id: int) -> None:
        async with session_scope() as session:
            result = await session.execute(delete(PrivatePaperRow).where(
                PrivatePaperRow.id == paper_id, PrivatePaperRow.user_id == user_id))
            if result.rowcount == 0:
                raise BusinessError(40401, '私有论文不存在', 404)
