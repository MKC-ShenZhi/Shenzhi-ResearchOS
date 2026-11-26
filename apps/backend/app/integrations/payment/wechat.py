import os
import httpx
from app.services.agent_entitlements.service import require, EntitlementError
from .base import PaymentFact


class WechatPayProvider:
    def __init__(self):
        self.app_id = os.getenv('WECHAT_APP_ID', '')
        self.merchant_id = os.getenv('WECHAT_MCH_ID', '')
        self.origin = os.getenv('PAYMENT_SERVICE_URL', '').rstrip('/')
        self.token = os.getenv('PAYMENT_SERVICE_TOKEN', '')
        require(all((self.app_id, self.merchant_id, self.origin, self.token)), 'WECHAT_NOT_CONFIGURED', 503)

    async def call(self, method, path, *, body=None, raw=None, headers=None):
        request_headers = {**(headers or {}), 'Authorization': 'Bearer ' + self.token}
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                response = await client.request(method, self.origin + path, json=body, content=raw, headers=request_headers)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise EntitlementError('WECHAT_SERVICE_FAILED', 502) from None

    async def create_order(self, order):
        return await self.call('POST', '/internal/wechat/orders', body={
            'order_id': order.order_id, 'amount': order.amount, 'currency': order.currency,
            'description': 'ShenZhi ' + order.plan_id})

    async def query_order(self, order):
        data = await self.call('GET', '/internal/wechat/orders/' + order.order_id)
        return PaymentFact(**data) if data else None

    async def verify_notification(self, body, headers):
        signed_headers = {k: v for k, v in headers.items() if k.lower().startswith('wechatpay-')}
        data = await self.call('POST', '/internal/wechat/verify-notification', raw=body,
                               headers={**signed_headers, 'Content-Type': 'application/json'})
        return PaymentFact(**data)
