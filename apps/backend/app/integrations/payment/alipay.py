"""Official Alipay SDK, desktop page payment and signed trade queries."""
import asyncio
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qsl
from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay.aop.api.domain.AlipayTradePagePayModel import AlipayTradePagePayModel
from alipay.aop.api.domain.AlipayTradeQueryModel import AlipayTradeQueryModel
from alipay.aop.api.request.AlipayTradePagePayRequest import AlipayTradePagePayRequest
from alipay.aop.api.request.AlipayTradeQueryRequest import AlipayTradeQueryRequest
from alipay.aop.api.util.SignatureUtils import get_sign_content, verify_with_rsa
from app.services.agent_entitlements.service import require, EntitlementError
from .base import PaymentFact


def fen(value):
    try:
        amount = Decimal(str(value)) * 100
        require(amount.is_finite() and amount > 0 and amount == amount.to_integral_value(), 'PAYMENT_AMOUNT_INVALID', 400)
        return int(amount)
    except (InvalidOperation, ValueError):
        raise EntitlementError('PAYMENT_AMOUNT_INVALID', 400) from None


class AlipayProvider:
    def __init__(self):
        self.app_id = os.getenv('ALIPAY_APP_ID', '')
        self.merchant_id = os.getenv('ALIPAY_SELLER_ID', '')
        self.notify_url = os.getenv('ALIPAY_NOTIFY_URL', '')
        self.return_url = os.getenv('ALIPAY_RETURN_URL', '')
        require(all((self.app_id, self.merchant_id, self.notify_url, self.return_url)), 'ALIPAY_NOT_CONFIGURED', 503)
        config = AlipayClientConfig(sandbox_debug=os.getenv('ALIPAY_SANDBOX') == 'true')
        if os.getenv('ALIPAY_SANDBOX') == 'true':
            config.server_url = 'https://openapi-sandbox.dl.alipaydev.com/gateway.do'
        config.app_id = self.app_id
        config.sign_type = 'RSA2'
        config.timeout = 15
        try:
            config.app_private_key = Path(os.environ['ALIPAY_PRIVATE_KEY_FILE']).read_text(encoding='utf-8').strip()
            config.alipay_public_key = Path(os.environ['ALIPAY_PUBLIC_KEY_FILE']).read_text(encoding='utf-8').strip()
        except (OSError, KeyError):
            raise EntitlementError('ALIPAY_KEYS_NOT_CONFIGURED', 503) from None
        self.public_key = config.alipay_public_key
        self.client = DefaultAlipayClient(config)  # No SDK logger: request signatures and payloads stay private.

    async def create_order(self, order):
        model = AlipayTradePagePayModel()
        model.out_trade_no = order.order_id
        model.total_amount = f'{order.amount // 100}.{order.amount % 100:02d}'
        model.subject = 'ShenZhi ' + order.plan_id
        model.product_code = 'FAST_INSTANT_TRADE_PAY'
        request = AlipayTradePagePayRequest(biz_model=model)
        request.notify_url = self.notify_url
        request.return_url = self.return_url
        try:
            url = await asyncio.to_thread(self.client.page_execute, request, 'GET')
        except Exception:
            raise EntitlementError('ALIPAY_CREATE_FAILED', 502) from None
        return {'kind': 'redirect', 'redirect_url': url}

    def fact(self, payload):
        require(payload.get('app_id') == self.app_id and payload.get('seller_id') == self.merchant_id,
                'PAYMENT_MERCHANT_MISMATCH', 400)
        # Domestic desktop payments are CNY. Query API omits trans_currency for domestic transactions.
        currency = payload.get('trans_currency') or 'CNY'
        require(currency == 'CNY', 'PAYMENT_CURRENCY_MISMATCH', 400)
        state = payload.get('trade_status')
        require(state in ('TRADE_SUCCESS', 'TRADE_FINISHED', 'WAIT_BUYER_PAY', 'TRADE_CLOSED'), 'PAYMENT_STATE_INVALID', 400)
        return PaymentFact(payload.get('out_trade_no', ''), payload.get('trade_no', ''), fen(payload.get('total_amount')),
            currency, payload['seller_id'], payload['app_id'],
            'paid' if state in ('TRADE_SUCCESS', 'TRADE_FINISHED') else 'closed' if state == 'TRADE_CLOSED' else 'pending')

    async def query_order(self, order):
        require((order.app_id, order.merchant_id) == (self.app_id, self.merchant_id), 'PAYMENT_MERCHANT_CHANGED')
        model = AlipayTradeQueryModel()
        model.out_trade_no = order.order_id
        try:
            # execute verifies the provider response signature using the configured Alipay public key.
            payload = json.loads(await asyncio.to_thread(self.client.execute, AlipayTradeQueryRequest(biz_model=model)))
        except Exception:
            raise EntitlementError('ALIPAY_QUERY_FAILED', 502) from None
        if payload.get('sub_code') == 'ACQ.TRADE_NOT_EXIST':
            return None
        require(payload.get('code') == '10000', 'ALIPAY_QUERY_FAILED', 502)
        # SDK 3.7.1467 TradeQuery has no App/seller identity fields. A signed
        # status alone cannot prove the recipient; wait for a verified notification.
        raise EntitlementError('PAYMENT_QUERY_IDENTITY_UNVERIFIED', 409)

    async def verify_notification(self, body, headers):
        try:
            pairs = parse_qsl(body.decode('utf-8'), keep_blank_values=True, strict_parsing=True)
            payload = dict(pairs)
            require(len(payload) == len(pairs) and payload.get('sign_type') == 'RSA2', 'PAYMENT_SIGNATURE_INVALID', 400)
            sign = payload.pop('sign', '')
            payload.pop('sign_type', None)
            payload = {k: v for k, v in payload.items() if v != ''}
            valid = verify_with_rsa(self.public_key, get_sign_content(payload).encode('utf-8'), sign)
        except EntitlementError:
            raise
        except Exception:
            raise EntitlementError('PAYMENT_SIGNATURE_INVALID', 400) from None
        require(valid, 'PAYMENT_SIGNATURE_INVALID', 400)
        return self.fact(payload)
