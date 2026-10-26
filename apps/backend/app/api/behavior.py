"""Authenticated, bounded ingestion for implicit paper interactions."""

from fastapi import APIRouter, Depends

from app.core.identity import RequestIdentity, require_user
from app.core.responses import ok
from app.schemas.behavior import BehaviorBatchRequest
from app.services.recommendation.behavior import BehaviorEventService

router = APIRouter(prefix='/api/v1/behavior-events', tags=['behavior-events'])
service = BehaviorEventService()


@router.post('/batch')
async def record_batch(body: BehaviorBatchRequest, identity: RequestIdentity = Depends(require_user)):
    count = await service.record_batch(identity.subject_id, body)
    return ok({'inserted': count})
