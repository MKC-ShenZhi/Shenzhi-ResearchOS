"""Personal recommendations are isolated from active knowledge search."""

from fastapi import APIRouter, Depends, Query

from app.core.identity import RequestIdentity, require_user
from app.core.responses import ok
from app.services.recommendation.profile import UserProfileService
from app.services.recommendation.recommendations import RecommendationService

router = APIRouter(prefix='/api/v1/recommendations', tags=['recommendations'])
service = RecommendationService()
profiles = UserProfileService()


@router.get('/papers')
async def papers(
    limit: int = Query(default=12, ge=1, le=48),
    cursor: str | None = Query(default=None, min_length=1, max_length=128),
    identity: RequestIdentity = Depends(require_user),
):
    return ok(await service.page(identity.subject_id, limit=limit, cursor=cursor))


@router.get('/me/profile')
async def my_profile(identity: RequestIdentity = Depends(require_user)):
    return ok(await profiles.get(identity.subject_id))
