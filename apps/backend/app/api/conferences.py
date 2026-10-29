"""Conference submission deadlines (CCF / CORE / THCPL ranked venues)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.errors import BusinessError
from app.core.identity import RequestIdentity, request_identity
from app.core.responses import ok
from app.services.conferences import (
    ConferenceDeadlineService,
    ConferenceFilters,
    ConferenceSnapshotError,
    UnknownCategoryError,
)


router = APIRouter(prefix='/api/v1/conferences', tags=['conferences'])
service = ConferenceDeadlineService()

UNAVAILABLE_MESSAGE = '会议截稿数据暂时不可用'


@router.get('')
async def deadlines(
    category: list[str] | None = Query(default=None, max_length=20),
    ccf: list[Literal['A', 'B', 'C', 'N']] | None = Query(default=None),
    core: list[Literal['A*', 'A', 'B', 'C', 'N']] | None = Query(default=None),
    thcpl: list[Literal['A', 'B', 'C', 'N']] | None = Query(default=None),
    status: list[Literal['open', 'tbd', 'closed']] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    _identity: RequestIdentity = Depends(request_identity),
):
    filters = ConferenceFilters(
        categories=frozenset(category or ()),
        ccf=frozenset(ccf or ()),
        core=frozenset(core or ()),
        thcpl=frozenset(thcpl or ()),
        statuses=frozenset(status or ()),
        query=q,
    )
    try:
        response = service.deadlines(filters)
    except UnknownCategoryError as error:
        raise BusinessError(20001, f'未知的研究方向：{error}', 422) from error
    except ConferenceSnapshotError as error:
        raise BusinessError(20004, UNAVAILABLE_MESSAGE, 503) from error
    return ok(response.model_dump(mode='json'))


@router.get('/categories')
async def categories(_identity: RequestIdentity = Depends(request_identity)):
    try:
        response = service.categories()
    except ConferenceSnapshotError as error:
        raise BusinessError(20004, UNAVAILABLE_MESSAGE, 503) from error
    return ok(response.model_dump(mode='json'))
