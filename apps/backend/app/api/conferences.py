"""Conference submission deadlines (CCF / CORE / THCPL ranked venues)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.core.errors import BusinessError
from app.core.identity import RequestIdentity, request_identity, require_user
from app.core.responses import ok
from app.schemas.conferences import ConferenceFollowState
from app.services.conferences import (
    ConferenceDeadlineService,
    ConferenceFilters,
    ConferenceSnapshotError,
    UnknownCategoryError,
)
from app.services.library.conference_follows import ConferenceFollowService


router = APIRouter(prefix='/api/v1/conferences', tags=['conferences'])
service = ConferenceDeadlineService()
follows = ConferenceFollowService()

UNAVAILABLE_MESSAGE = '会议截稿数据暂时不可用'


@router.get('')
async def deadlines(
    request: Request,
    category: list[str] | None = Query(default=None, max_length=20),
    ccf: list[Literal['A', 'B', 'C', 'N']] | None = Query(default=None),
    core: list[Literal['A*', 'A', 'B', 'C', 'N']] | None = Query(default=None),
    thcpl: list[Literal['A', 'B', 'C', 'N']] | None = Query(default=None),
    status: list[Literal['open', 'tbd', 'closed']] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    followed: bool = Query(default=False),
    _identity: RequestIdentity = Depends(request_identity),
):
    # `followed=true` narrows the same filtered list to the signed-in user's follows.
    followed_ids = await follows.followed_ids(require_user(request).subject_id) if followed else None
    filters = ConferenceFilters(
        ids=followed_ids,
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


def _followable_conference(conference_id: str) -> str:
    try:
        exists = service.has_conference(conference_id)
    except ConferenceSnapshotError as error:
        raise BusinessError(20004, UNAVAILABLE_MESSAGE, 503) from error
    if not exists:
        raise BusinessError(40401, '未找到对应会议', 404)
    return conference_id


@router.put('/{conference_id}/follow')
async def follow_conference(conference_id: str, identity: RequestIdentity = Depends(require_user)):
    await follows.follow(identity.subject_id, _followable_conference(conference_id))
    return ok(ConferenceFollowState(conference_id=conference_id, is_following=True).model_dump(mode='json'))


@router.delete('/{conference_id}/follow')
async def unfollow_conference(conference_id: str, identity: RequestIdentity = Depends(require_user)):
    await follows.unfollow(identity.subject_id, conference_id)
    return ok(ConferenceFollowState(conference_id=conference_id, is_following=False).model_dump(mode='json'))
