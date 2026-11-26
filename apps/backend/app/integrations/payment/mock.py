from .base import PaymentFact
from app.services.agent_entitlements.service import require


class MockPaymentProvider:
    merchant_id = 'mock-merchant'
    app_id = 'mock-app'

    def __init__(self, channel):
        self.channel = channel

    async def create_order(self, order):
        return {'kind': 'mock', 'channel': self.channel}

    async def query_order(self, order):
        return None  # Mock confirmation is explicitly persisted by the dev-only API.

    async def verify_notification(self, body, headers):
        require(False, 'MOCK_WEBHOOK_DISABLED', 404)

    def success(self, order):
        return PaymentFact(order.order_id, 'mock-' + order.order_id, order.amount,
                           order.currency, self.merchant_id, self.app_id, 'paid')
