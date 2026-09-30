"""Database-only API for the home discovery feed."""

from fastapi import APIRouter, Depends, Query

from app.core.identity import RequestIdentity, request_identity
from app.core.responses import ok
from app.schemas.discovery import DiscoveryFeedTab
from app.services.daily_recommendations import DailyRecommendationService


router = APIRouter(prefix='/api/v1/discovery', tags=['discovery'])
service = DailyRecommendationService()


@router.get('/recommendations')
async def recommendations(
    tab: DiscoveryFeedTab = Query(default='recommend'),
    limit: int = Query(default=8, ge=1, le=20),
    identity: RequestIdentity = Depends(request_identity),
):
    response = await service.recommendations(identity, tab=tab, limit=limit)
    return ok(response.model_dump(mode='json', by_alias=True))
