"""Collection folder and paper membership operations."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.collections import CollectionFolderRow, CollectionItemRow, CollectionUserStateRow
from app.models.private_paper import PrivatePaperRow
from app.schemas.collections import (
    CollectionFolder,
    CollectionPaperItem,
    CollectionPaperListResponse,
    FolderListResponse,
)
from app.services.knowledge.service import KnowledgeService

DEFAULT_FOLDERS = ('想读', '在读', '已读')


class CollectionService:
    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def ensure_default_folders(self, user_id: str) -> None:
        async with session_scope() as session:
            inserted_user = await session.scalar(
                insert(CollectionUserStateRow)
                .values(user_id=user_id)
                .on_conflict_do_nothing(index_elements=['user_id'])
                .returning(CollectionUserStateRow.user_id)
            )
            if inserted_user is None:
                return

            # Existing rows can come from the first version of this feature.
            # Mark those users initialized without recreating deleted defaults.
            has_folders = await session.scalar(select(CollectionFolderRow.id).where(CollectionFolderRow.user_id == user_id).limit(1))
            if has_folders is None:
                for name in DEFAULT_FOLDERS:
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
            private_counts = dict((folder_id, count) for folder_id, count in await session.execute(
                select(PrivatePaperRow.folder_id, func.count(PrivatePaperRow.id))
                .where(PrivatePaperRow.user_id == user_id, PrivatePaperRow.folder_id.in_([row.id for row in rows]))
                .group_by(PrivatePaperRow.folder_id)
            )) if rows else {}
        return FolderListResponse(folders=[CollectionFolder(
            id=row.id, name=row.name, is_default=row.is_default,
            paper_count=counts.get(row.id, 0) + private_counts.get(row.id, 0),
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
            private_count = await session.scalar(select(func.count(PrivatePaperRow.id)).where(
                PrivatePaperRow.folder_id == folder_id, PrivatePaperRow.user_id == user_id))
            return CollectionFolder(id=row.id, name=row.name, is_default=row.is_default,
                                    paper_count=(count or 0) + (private_count or 0))

    async def delete_folder(self, user_id: str, folder_id: int) -> None:
        await self.ensure_default_folders(user_id)
        async with session_scope() as session:
            await self._lock_membership(session, user_id)
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
        summaries = await self.knowledge.batch_get_papers([row.paper_id for row in rows])
        summaries_by_id = {paper.id: paper for paper in summaries}
        items = [CollectionPaperItem.model_validate({
            **self._paper_data(summaries_by_id.get(row.paper_id), row.paper_id),
            'paper_id': row.paper_id,
            'added_at': row.created_at,
        }) for row in rows]
        return CollectionPaperListResponse(items=items, total=total or 0, page=page, page_size=page_size)

    async def collected_papers(self, user_id: str, page: int, page_size: int) -> CollectionPaperListResponse:
        """One row per paper across this user's folders, newest collection first."""
        async with session_scope() as session:
            grouped = (
                select(
                    CollectionItemRow.paper_id.label('paper_id'),
                    func.max(CollectionItemRow.created_at).label('added_at'),
                )
                .join(CollectionFolderRow, CollectionFolderRow.id == CollectionItemRow.folder_id)
                .where(CollectionFolderRow.user_id == user_id)
                .group_by(CollectionItemRow.paper_id)
                .subquery()
            )
            rows = list(await session.execute(
                select(grouped.c.paper_id, grouped.c.added_at)
                .order_by(grouped.c.added_at.desc(), grouped.c.paper_id)
                .offset((page - 1) * page_size).limit(page_size)
            ))
            total = await session.scalar(select(func.count()).select_from(grouped))
        summaries = await self.knowledge.batch_get_papers([paper_id for paper_id, _ in rows])
        summaries_by_id = {paper.id: paper for paper in summaries}
        items = [CollectionPaperItem.model_validate({
            **self._paper_data(summaries_by_id.get(paper_id), paper_id),
            'paper_id': paper_id,
            'added_at': added_at,
        }) for paper_id, added_at in rows]
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
            await self._lock_membership(session, user_id)
            folders = list(await session.scalars(select(CollectionFolderRow).where(
                CollectionFolderRow.user_id == user_id, CollectionFolderRow.id.in_(set(folder_ids)),
            ).order_by(CollectionFolderRow.id).with_for_update())) if folder_ids else []
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
        await self.ensure_default_folders(user_id)
        async with session_scope() as session:
            await self._lock_membership(session, user_id)
            await self._folder(session, user_id, folder_id)
            result = await session.execute(delete(CollectionItemRow).where(
                CollectionItemRow.folder_id == folder_id, CollectionItemRow.paper_id == paper_id,
            ))
            if result.rowcount == 0:
                raise BusinessError(40401, '论文不在该文件夹中', 404)

    async def move_paper(self, user_id: str, folder_id: int, paper_id: str, target_folder_id: int) -> None:
        if folder_id == target_folder_id:
            raise BusinessError(40004, '目标文件夹不能与当前文件夹相同', 400)
        await self.ensure_default_folders(user_id)
        async with session_scope() as session:
            await self._lock_membership(session, user_id)
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
                count = await session.scalar(select(func.count(CollectionItemRow.id)).where(
                    CollectionItemRow.folder_id == target_folder_id,
                ))
                if (count or 0) >= 100:
                    raise BusinessError(40005, '每个文件夹最多收藏 100 篇论文', 400)
                session.add(CollectionItemRow(folder_id=target_folder_id, paper_id=paper_id))

    @staticmethod
    async def _lock_membership(session, user_id: str) -> None:
        # A replacement can target disjoint folders (or the empty set). Lock a
        # stable per-account row so replace/move/remove/delete serialize alike.
        await session.execute(select(CollectionUserStateRow).where(
            CollectionUserStateRow.user_id == user_id,
        ).with_for_update())

    async def collector_counts(self, paper_ids: list[str]) -> dict[str, int]:
        """Distinct users per paper across every folder.

        One user holding the same paper in three folders counts once; moving a
        paper between folders does not change the number.
        """
        ids = list(dict.fromkeys(paper_ids))
        if not ids:
            return {}
        async with session_scope() as session:
            rows = await session.execute(
                select(
                    CollectionItemRow.paper_id,
                    func.count(func.distinct(CollectionFolderRow.user_id)),
                )
                .join(CollectionFolderRow, CollectionFolderRow.id == CollectionItemRow.folder_id)
                .where(CollectionItemRow.paper_id.in_(ids))
                .group_by(CollectionItemRow.paper_id)
            )
            return {paper_id: int(total) for paper_id, total in rows}

    @staticmethod
    def _paper_data(summary, paper_id: str) -> dict:
        if summary is not None:
            return {**summary.model_dump(), 'is_available': True}
        return {
            'id': paper_id,
            'title': '论文暂不可用',
            'provenance': {'external_id': paper_id},
            'is_available': False,
        }

    async def paper_folder_map(self, user_id: str, paper_ids: list[str]) -> dict[str, list[int]]:
        """Personal folder membership for a visible list, without one query per card."""
        ids = list(dict.fromkeys(paper_ids))
        if not ids:
            return {}
        async with session_scope() as session:
            rows = await session.execute(
                select(CollectionItemRow.paper_id, CollectionItemRow.folder_id)
                .join(CollectionFolderRow, CollectionFolderRow.id == CollectionItemRow.folder_id)
                .where(
                    CollectionFolderRow.user_id == user_id,
                    CollectionItemRow.paper_id.in_(ids),
                )
            )
            membership: dict[str, list[int]] = {}
            for paper_id, folder_id in rows:
                membership.setdefault(paper_id, []).append(folder_id)
        return {paper_id: sorted(folder_ids) for paper_id, folder_ids in membership.items()}

    async def _folder(self, session, user_id: str, folder_id: int) -> CollectionFolderRow:
        row = await session.scalar(select(CollectionFolderRow).where(
            CollectionFolderRow.id == folder_id, CollectionFolderRow.user_id == user_id,
        ))
        if row is None:
            raise BusinessError(40402, '文件夹不存在', 404)
        return row
