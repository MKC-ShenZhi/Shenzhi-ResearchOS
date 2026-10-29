"""Read-only platform aggregates for the Knowledge Base service identity."""
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.errors import BusinessError
from app.core.identity import require_stats_service
from app.core.responses import ok
from app.services.stats.service import MAX_LOOKUP_IDS, PlatformStatsService


router = APIRouter(prefix='/api/v1/stats', tags=['stats'])
service = PlatformStatsService()


def _snapshot_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise BusinessError(20001, '日期必须是 YYYY-MM-DD', 400) from None


def _lookup_ids(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    normalized: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item != value or len(item) > 300:
            raise BusinessError(20001, 'ID 不合法', 422)
        if item not in normalized:
            normalized.append(item)
    if len(normalized) > MAX_LOOKUP_IDS:
        raise BusinessError(20001, f'一次最多查询 {MAX_LOOKUP_IDS} 个 ID', 422)
    return normalized


@router.get('/meta')
async def meta(_service: None = Depends(require_stats_service)):
    return ok((await service.meta()).model_dump(mode='json'))


@router.get('/papers')
async def paper_stats(
    snapshot_date: str | None = Query(default=None, alias='date'),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None, min_length=1, max_length=2048),
    paper_id: list[str] | None = Query(default=None),
    _service: None = Depends(require_stats_service),
):
    page = await service.papers_page(
        snapshot_date=_snapshot_date(snapshot_date),
        limit=limit,
        cursor=cursor,
        paper_ids=_lookup_ids(paper_id),
    )
    return ok(page.model_dump(mode='json'))


@router.get('/topics')
async def topic_stats(
    snapshot_date: str | None = Query(default=None, alias='date'),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None, min_length=1, max_length=2048),
    topic_id: list[str] | None = Query(default=None),
    _service: None = Depends(require_stats_service),
):
    page = await service.topics_page(
        snapshot_date=_snapshot_date(snapshot_date),
        limit=limit,
        cursor=cursor,
        topic_ids=_lookup_ids(topic_id),
    )
    return ok(page.model_dump(mode='json'))
