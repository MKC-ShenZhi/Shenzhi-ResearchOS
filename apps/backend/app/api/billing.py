from fastapi import APIRouter, Depends
from app.core.identity import require_user
from app.core.responses import ok
from app.schemas.billing import CreateOrder, QuoteRequest
from app.services.billing import service

router = APIRouter(prefix='/api/v1/billing', tags=['billing'])


@router.get('/plans')
async def plans(_identity=Depends(require_user)):
    return ok(await service.plans())


@router.get('/subscription')
async def subscription(identity=Depends(require_user)):
    return ok(await service.subscription(identity.subject_id))


@router.post('/orders')
async def create_order(body: CreateOrder, identity=Depends(require_user)):
    return ok(await service.create_order(identity.subject_id, body))


@router.post('/quote')
async def quote(body: QuoteRequest, identity=Depends(require_user)):
    return ok(await service.quote(identity.subject_id, body.plan_id))


@router.get('/orders')
async def orders(identity=Depends(require_user)):
    return ok(await service.list_orders(identity.subject_id))


@router.get('/orders/{order_id}')
async def order(order_id: str, identity=Depends(require_user)):
    return ok(await service.get_order(identity.subject_id, order_id))


@router.post('/orders/{order_id}/refresh')
async def refresh(order_id: str, identity=Depends(require_user)):
    return ok(await service.refresh(identity.subject_id, order_id))


@router.post('/orders/{order_id}/payment')
async def payment(order_id: str, identity=Depends(require_user)):
    return ok(await service.prepare_payment(identity.subject_id, order_id))


@router.post('/orders/{order_id}/mock-pay')
async def mock_pay(order_id: str, identity=Depends(require_user)):
    return ok(await service.mock_pay(identity.subject_id, order_id))
