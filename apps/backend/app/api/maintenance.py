"""Secret-protected maintenance endpoints invoked by the deployment scheduler."""

import asyncio
import logging
import hmac
import os

from fastapi import APIRouter, HTTPException, Request

from app.core.responses import ok
from app.services.recommendation.maintenance import purge_expired
from app.services.conferences_sync import ConferenceSync

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/internal', tags=['internal-maintenance'])


def require_cron_secret(request: Request) -> None:
    secret = os.getenv('CRON_SECRET', '').strip()
    if not secret:
        raise HTTPException(status_code=503, detail='Scheduled maintenance is not configured')
    authorization = request.headers.get('authorization', '')
    if not hmac.compare_digest(authorization.encode('utf-8'), f'Bearer {secret}'.encode('utf-8')):
        raise HTTPException(status_code=401, detail='Unauthorized')


@router.get('/recommendation-maintenance')
async def recommendation_maintenance(request: Request):
    require_cron_secret(request)
    deleted_events, deleted_snapshots = await purge_expired()
    return ok({
        'deleted_events': deleted_events,
        'deleted_recommendation_snapshots': deleted_snapshots,
    })


@router.get('/conference-sync')
async def conference_sync(request: Request):
    """Await the shared job inside the request; never spawn a background task."""
    require_cron_secret(request)
    if os.getenv('CONFERENCE_CRON_ENABLED', '').strip().lower() not in {'1', 'true', 'yes', 'on'}:
        raise HTTPException(status_code=503, detail='Conference cron is disabled')
    if not os.getenv('CHAT_DATABASE_URL', '').strip():
        raise HTTPException(status_code=503, detail='Conference database is not configured')
    try:
        # Leave 60 seconds below Vercel's 300-second limit for cancellation/response.
        async with asyncio.timeout(240):
            result = await ConferenceSync().run()
    except TimeoutError:
        logger.exception('Conference cron timed out; existing snapshot is kept')
        raise HTTPException(status_code=504, detail='Conference sync timed out') from None
    except Exception:
        logger.exception('Conference cron failed; existing snapshot is kept')
        raise HTTPException(status_code=503, detail='Conference sync failed') from None
    response = ok(result)
    response.headers['Cache-Control'] = 'no-store'
    return response
