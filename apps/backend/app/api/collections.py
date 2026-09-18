"""Authenticated collection folder and paper routes."""
from fastapi import APIRouter, Depends, Query, Response, status

from app.core.identity import RequestIdentity, require_user
from app.core.responses import ok
from app.schemas.collections import (
    FolderCreateRequest, FolderUpdateRequest, MoveCollectionItemRequest,
    PaperCollectionUpdateRequest,
)
from app.services.collections import CollectionService


router = APIRouter(prefix='/api/v1', tags=['collections'])
service = CollectionService()


@router.get('/collections/folders')
async def folders(identity: RequestIdentity = Depends(require_user)):
    return ok((await service.folders(identity.subject_id)).model_dump(mode='json'))


@router.post('/collections/folders', status_code=status.HTTP_201_CREATED)
async def create_folder(body: FolderCreateRequest, identity: RequestIdentity = Depends(require_user)):
    return ok((await service.create_folder(identity.subject_id, body.name)).model_dump(mode='json'))


@router.patch('/collections/folders/{folder_id}')
async def rename_folder(folder_id: int, body: FolderUpdateRequest, identity: RequestIdentity = Depends(require_user)):
    return ok((await service.rename_folder(identity.subject_id, folder_id, body.name)).model_dump(mode='json'))


@router.delete('/collections/folders/{folder_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: int, identity: RequestIdentity = Depends(require_user)):
    await service.delete_folder(identity.subject_id, folder_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/collections/folders/{folder_id}/papers')
async def folder_papers(
    folder_id: int,
    identity: RequestIdentity = Depends(require_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=20),
):
    return ok((await service.papers(identity.subject_id, folder_id, page, page_size)).model_dump(mode='json'))


@router.get('/papers/{paper_id}/collections')
async def paper_collections(paper_id: str, identity: RequestIdentity = Depends(require_user)):
    return ok({'folder_ids': await service.paper_folders(identity.subject_id, paper_id)})


@router.put('/papers/{paper_id}/collections')
async def update_paper_collections(
    paper_id: str,
    body: PaperCollectionUpdateRequest,
    identity: RequestIdentity = Depends(require_user),
):
    await service.update_paper_folders(identity.subject_id, paper_id, body.folder_ids)
    return ok({'success': True})


@router.delete('/collections/folders/{folder_id}/papers/{paper_id}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_paper(folder_id: int, paper_id: str, identity: RequestIdentity = Depends(require_user)):
    await service.remove_paper(identity.subject_id, folder_id, paper_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/collections/folders/{folder_id}/papers/{paper_id}/move')
async def move_paper(
    folder_id: int,
    paper_id: str,
    body: MoveCollectionItemRequest,
    identity: RequestIdentity = Depends(require_user),
):
    await service.move_paper(identity.subject_id, folder_id, paper_id, body.target_folder_id)
    return ok({'success': True})