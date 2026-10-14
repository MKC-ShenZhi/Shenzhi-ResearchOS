"""Authenticated paper reading history routes."""
from fastapi import APIRouter, Depends, Query

from app.core.identity import RequestIdentity, require_user
from app.core.responses import ok
from app.schemas.history import PaperReadStatusRequest, PaperReadStatusResponse, PaperViewRequest
from app.services.library.reading_history import ReadingHistoryService


router = APIRouter(tags=['history'])
service = ReadingHistoryService()


@router.post('/api/v1/papers/read-status')
async def paper_read_status(body: PaperReadStatusRequest, identity: RequestIdentity = Depends(require_user)):
    read_paper_ids, reading_paper_ids = await service.paper_status_ids(identity.subject_id, body.paper_ids)
    return ok(PaperReadStatusResponse(
        user_id=identity.subject_id,
        read_paper_ids=read_paper_ids,
        reading_paper_ids=reading_paper_ids,
    ).model_dump())


@router.post('/api/v1/papers/read')
async def mark_paper_read(body: PaperViewRequest, identity: RequestIdentity = Depends(require_user)):
    await service.mark_read(identity.subject_id, body.paper_id)
    return ok({'success': True, 'user_id': identity.subject_id})


@router.post('/api/v1/papers/view')
async def record_paper_view(body: PaperViewRequest, identity: RequestIdentity = Depends(require_user)):
    await service.record(identity.subject_id, body.paper_id)
    return ok({'success': True, 'user_id': identity.subject_id})


@router.post('/api/v1/papers/{paper_id}/view')
async def record_view(paper_id: str, identity: RequestIdentity = Depends(require_user)):
    if not paper_id.strip():
        return ok({'success': False, 'user_id': identity.subject_id})
    await service.record(identity.subject_id, paper_id)
    return ok({'success': True, 'user_id': identity.subject_id})


@router.get('/api/v1/history')
async def history(
    identity: RequestIdentity = Depends(require_user),
    page: int = Query(default=1, ge=1, le=5),
    page_size: int = Query(default=20, ge=1, le=20),
    query: str = Query(default='', max_length=200),
):
    response = await service.list(identity.subject_id, page, page_size, query.strip())
    return ok(response.model_dump(mode='json', by_alias=True))
