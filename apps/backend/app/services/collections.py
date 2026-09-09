"""Collection folder and paper membership operations."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.collections import CollectionFolderRow, CollectionItemRow
from app.schemas.collections import (
    CollectionFolder,
    CollectionPaperItem,
    CollectionPaperListResponse,
    FolderListResponse,
)
from app.services.knowledge import KnowledgeService

DEFAULT_FOLDERS = ('想读', '在读', '已读')


class CollectionService:
    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def ensure_default_folders(self, user_id: str) -> None:
        async with session_scope() as session:
            existing = set(await session.scalars(
                select(CollectionFolderRow.name).where(CollectionFolderRow.user_id == user_id)
            ))
            for name in DEFAULT_FOLDERS:
                if name not in existing:
                    session.add(CollectionFolderRow(user_id=user_id, name=name, is_default=True))

    async def folders(self, user_id: str) -> FolderListResponse:
        await self.ensure_default_folders(user_id)
        async with session_scope() as session:
            rows = list(await session.scalars(
                select(CollectionFolderRow)
                .where(CollectionFolderRow.user_id == user_id)
                .order_by(CollectionFolderRow.created_at, CollectionFolderRow.id)
            ))
            counts = dict((folder_id, count) for folder_id, count in await session.execute(
                select(CollectionItemRow.folder_id, func.count(CollectionItemRow.id))
                .where(CollectionItemRow.folder_id.in_([row.id for row in rows]))
                .group_by(CollectionItemRow.folder_id)
            )) if rows else {}
        return FolderListResponse(folders=[CollectionFolder(
            id=row.id, name=row.name, is_default=row.is_default, paper_count=counts.get(row.id, 0),
        ) for row in rows])

    async def create_folder(self, user_id: str, name: str) -> CollectionFolder:
        name = name.strip()
        if not name:
            raise BusinessError(40001, '文件夹名称不能为空', 422)
        async with session_scope() as session:
            duplicate = await session.scalar(select(CollectionFolderRow).where(
                CollectionFolderRow.user_id == user_id, CollectionFolderRow.name == name,
            ))
            if duplicate:
                raise BusinessError(40002, '名称已存在', 409)
            row = CollectionFolderRow(user_id=user_id, name=name)
            session.add(row)
            await session.flush()
            return CollectionFolder(id=row.id, name=row.name, is_default=False, paper_count=0)

    async def rename_folder(self, user_id: str, folder_id: int, name: str) -> CollectionFolder:
        name = name.strip()
        if not name:
            raise BusinessError(40001, '文件夹名称不能为空', 422)
        async with session_scope() as session:
            row = await self._folder(session, user_id, folder_id)
            duplicate = await session.scalar(select(CollectionFolderRow).where(
                CollectionFolderRow.user_id == user_id,
                CollectionFolderRow.name == name,
                CollectionFolderRow.id != folder_id,
            ))
            if duplicate:
                raise BusinessError(40002, '名称已存在', 409)
            row.name = name
            row.updated_at = datetime.now(timezone.utc)
            count = await session.scalar(select(func.count(CollectionItemRow.id)).where(CollectionItemRow.folder_id == folder_id))
            return CollectionFolder(id=row.id, name=row.name, is_default=row.is_default, paper_count=count or 0)

    async def delete_folder(self, user_id: str, folder_id: int) -> None:
        async with session_scope() as session:
            await self._folder(session, user_id, folder_id)
            await session.execute(delete(CollectionFolderRow).where(
                CollectionFolderRow.id == folder_id, CollectionFolderRow.user_id == user_id,
            ))

    async def papers(self, user_id: str, folder_id: int, page: int, page_size: int) -> CollectionPaperListResponse:
        async with session_scope() as session:
            await self._folder(session, user_id, folder_id)
            rows = list((await session.execute(
                select(CollectionItemRow)
                .where(CollectionItemRow.folder_id == folder_id)
                .order_by(CollectionItemRow.created_at.desc(), CollectionItemRow.id.desc())
                .offset((page - 1) * page_size).limit(page_size)
            )).scalars())
            total = await session.scalar(select(func.count(CollectionItemRow.id)).where(CollectionItemRow.folder_id == folder_id))
        items = []
        for row in rows:
            try:
                paper = await self.knowledge.get_paper(row.paper_id)
            except Exception as error:
                if getattr(error, 'status_code', None) == 404 or getattr(getattr(error, 'error', None), 'code', None) == 'NOT_FOUND':
                    continue
                raise
            items.append(CollectionPaperItem.model_validate({
                **paper.model_dump(), 'paper_id': row.paper_id, 'added_at': row.created_at,
            }))
        return CollectionPaperListResponse(items=items, total=total or 0, page=page, page_size=page_size)

    async def paper_folders(self, user_id: str, paper_id: str) -> list[int]:
        await self.ensure_default_folders(user_id)
        async with session_scope() as session:
            return list(await session.scalars(select(CollectionItemRow.folder_id).join(
                CollectionFolderRow, CollectionFolderRow.id == CollectionItemRow.folder_id,
            ).where(CollectionFolderRow.user_id == user_id, CollectionItemRow.paper_id == paper_id)))

    async def update_paper_folders(self, user_id: str, paper_id: str, folder_ids: list[int]) -> None:
        await self.ensure_default_folders(user_id)
        async with session_scope() as session:
            folders = list(await session.scalars(select(CollectionFolderRow).where(
                CollectionFolderRow.user_id == user_id, CollectionFolderRow.id.in_(set(folder_ids)),
            ))) if folder_ids else []
            if len(folders) != len(set(folder_ids)):
                raise BusinessError(40003, '包含不存在的文件夹', 400)
            existing = set(await session.scalars(select(CollectionItemRow.folder_id).where(
                CollectionItemRow.paper_id == paper_id,
                CollectionItemRow.folder_id.in_(select(CollectionFolderRow.id).where(CollectionFolderRow.user_id == user_id)),
            )))
            desired = set(folder_ids)
            if existing - desired:
                await session.execute(delete(CollectionItemRow).where(
                    CollectionItemRow.paper_id == paper_id, CollectionItemRow.folder_id.in_(existing - desired),
                ))
            for folder_id in desired - existing:
                count = await session.scalar(select(func.count(CollectionItemRow.id)).where(CollectionItemRow.folder_id == folder_id))
                if (count or 0) >= 100:
                    raise BusinessError(40005, '每个文件夹最多收藏 100 篇论文', 400)
                session.add(CollectionItemRow(folder_id=folder_id, paper_id=paper_id))

    async def remove_paper(self, user_id: str, folder_id: int, paper_id: str) -> None:
        async with session_scope() as session:
            await self._folder(session, user_id, folder_id)
            result = await session.execute(delete(CollectionItemRow).where(
                CollectionItemRow.folder_id == folder_id, CollectionItemRow.paper_id == paper_id,
            ))
            if result.rowcount == 0:
                raise BusinessError(40401, '论文不在该文件夹中', 404)

    async def move_paper(self, user_id: str, folder_id: int, paper_id: str, target_folder_id: int) -> None:
        if folder_id == target_folder_id:
            raise BusinessError(40004, '目标文件夹不能与当前文件夹相同', 400)
        async with session_scope() as session:
            await self._folder(session, user_id, folder_id)
            await self._folder(session, user_id, target_folder_id)
            result = await session.execute(delete(CollectionItemRow).where(
                CollectionItemRow.folder_id == folder_id, CollectionItemRow.paper_id == paper_id,
            ))
            if result.rowcount == 0:
                raise BusinessError(40401, '论文不在该文件夹中', 404)
            exists = await session.scalar(select(CollectionItemRow).where(
                CollectionItemRow.folder_id == target_folder_id, CollectionItemRow.paper_id == paper_id,
            ))
            if not exists:
                session.add(CollectionItemRow(folder_id=target_folder_id, paper_id=paper_id))

    async def _folder(self, session, user_id: str, folder_id: int) -> CollectionFolderRow:
        row = await session.scalar(select(CollectionFolderRow).where(
            CollectionFolderRow.id == folder_id, CollectionFolderRow.user_id == user_id,
        ))
        if row is None:
            raise BusinessError(40402, '文件夹不存在', 404)
        return row