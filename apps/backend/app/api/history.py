"""Authenticated paper reading history routes."""
from fastapi import APIRouter, Depends, Query

from app.core.identity import RequestIdentity, require_user
from app.core.responses import ok
from app.services.reading_history import ReadingHistoryService


router = APIRouter(tags=['history'])
service = ReadingHistoryService()


@router.post('/api/v1/papers/{paper_id}/view')
async def record_view(paper_id: str, identity: RequestIdentity = Depends(require_user)):
    if not paper_id.strip():
        return ok({'success': False})
    await service.record(identity.subject_id, paper_id)
    return ok({'success': True})


@router.get('/api/v1/history')
async def history(
    identity: RequestIdentity = Depends(require_user),
    page: int = Query(default=1, ge=1, le=5),
    page_size: int = Query(default=20, ge=1, le=20),
    query: str = Query(default='', max_length=200),
):
    response = await service.list(identity.subject_id, page, page_size, query.strip())
    return ok(response.model_dump(mode='json', by_alias=True))