"""Secret-protected maintenance endpoints invoked by the deployment scheduler."""

import hmac
import os

from fastapi import APIRouter, HTTPException, Request

from app.core.responses import ok
from app.services.recommendation.maintenance import purge_expired

router = APIRouter(prefix='/api/v1/internal', tags=['internal-maintenance'])


@router.get('/recommendation-maintenance')
async def recommendation_maintenance(request: Request):
    secret = os.getenv('CRON_SECRET', '').strip()
    if not secret:
        raise HTTPException(status_code=503, detail='Scheduled maintenance is not configured')
    authorization = request.headers.get('authorization', '')
    if not hmac.compare_digest(authorization, f'Bearer {secret}'):
        raise HTTPException(status_code=401, detail='Unauthorized')

    deleted_events, deleted_snapshots = await purge_expired()
    return ok({
        'deleted_events': deleted_events,
        'deleted_recommendation_snapshots': deleted_snapshots,
    })
