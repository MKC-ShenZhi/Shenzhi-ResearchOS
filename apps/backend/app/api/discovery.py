"""Stable, knowledge-service-independent API for the home discovery feed."""

from fastapi import APIRouter, Depends, Query

from app.core.errors import BusinessError
from app.core.identity import RequestIdentity, request_identity
from app.core.responses import ok
from app.services.discovery import (
    DiscoveryCursorError,
    DiscoverySnapshotError,
    HomeDiscoveryService,
)


router = APIRouter(prefix='/api/v1/discovery', tags=['discovery'])
service = HomeDiscoveryService()


@router.get('/papers')
async def papers(
    limit: int = Query(default=12, ge=1, le=48),
    cursor: str | None = Query(default=None, min_length=1, max_length=512),
    _identity: RequestIdentity = Depends(request_identity),
):
    try:
        response = service.page(limit=limit, cursor=cursor)
    except DiscoveryCursorError as error:
        raise BusinessError(20001, str(error), 400) from error
    except DiscoverySnapshotError as error:
        raise BusinessError(20004, '论文发现数据暂时不可用', 503) from error
    return ok(response.model_dump(mode='json', by_alias=True))
