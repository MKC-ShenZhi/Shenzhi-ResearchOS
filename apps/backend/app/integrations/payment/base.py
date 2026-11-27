"""Small provider contract; only verified facts reach business confirmation."""
from dataclasses import dataclass
from typing import Protocol
import os
from app.services.agent_entitlements.service import require


@dataclass(frozen=True)
class PaymentFact:
    order_id: str
    transaction_id: str
    amount: int
    currency: str
    merchant_id: str
    app_id: str
    status: str  # paid / pending / closed


class PaymentProvider(Protocol):
    merchant_id: str
    app_id: str
    async def create_order(self, order) -> dict: ...
    async def query_order(self, order) -> PaymentFact | None: ...
    async def verify_notification(self, body: bytes, headers: dict) -> PaymentFact: ...


def mode():
    value = os.getenv('BILLING_PAYMENT_MODE', 'disabled')
    require(value in ('mock', 'live'), 'PAYMENTS_DISABLED', 503)
    if value == 'mock':
        require(os.getenv('BILLING_MOCK_ENABLED') == 'true' and
                os.getenv('ENVIRONMENT') in ('development', 'test'), 'MOCK_PAYMENT_DISABLED', 503)
    return value


def provider(channel, expected_mode=None) -> PaymentProvider:
    current = mode()
    require(expected_mode is None or expected_mode == current, 'PAYMENT_MODE_CHANGED')
    if current == 'mock':
        from .mock import MockPaymentProvider
        return MockPaymentProvider(channel)
    if channel == 'alipay':
        from .alipay import AlipayProvider
        return AlipayProvider()
    require(channel == 'wechat', 'PAYMENT_CHANNEL_INVALID', 422)
    from .wechat import WechatPayProvider
    return WechatPayProvider()
