"""Public provider callbacks, independent of BFF/user identity."""
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response
from app.integrations.payment.base import provider, mode
from app.services.agent_entitlements.service import require
from app.services.billing.service import confirm

router = APIRouter(prefix='/api/v1/payment-webhooks', tags=['payment-webhooks'])


@router.post('/{channel}')
async def notification(channel: str, request: Request):
    require(channel in ('alipay', 'wechat'), 'PAYMENT_CHANNEL_INVALID', 404)
    require(mode() == 'live', 'LIVE_PAYMENT_REQUIRED', 404)
    adapter = provider(channel, 'live')
    fact = await adapter.verify_notification(await request.body(), dict(request.headers))
    await confirm(channel, 'live', fact)
    # Acknowledge confirmed payment even when fulfillment is waiting for grant drain.
    return PlainTextResponse('success') if channel == 'alipay' else Response(status_code=204)
