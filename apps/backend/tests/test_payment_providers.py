"""Real official SDK signatures with ephemeral test-only keys; no merchant calls."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit, parse_qs

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from alipay.aop.api.util.SignatureUtils import sign_with_rsa2
from app.integrations.payment.alipay import AlipayProvider, fen
from app.integrations.payment.base import provider
from app.integrations.payment.wechat import WechatPayProvider
from app.services.agent_entitlements.service import EntitlementError
import httpx


class AlipayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                         serialization.NoEncryption()).decode()
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        (directory / 'private.pem').write_text(self.private)
        (directory / 'public.pem').write_text(public)
        self.enterContext(patch.dict(os.environ, {'ALIPAY_APP_ID': 'test-app', 'ALIPAY_SELLER_ID': 'test-seller',
            'ALIPAY_PRIVATE_KEY_FILE': str(directory / 'private.pem'), 'ALIPAY_PUBLIC_KEY_FILE': str(directory / 'public.pem'),
            'ALIPAY_NOTIFY_URL': 'https://web.example.test/api/payment-notifications/alipay',
            'ALIPAY_RETURN_URL': 'https://web.example.test/settings?tab=subscription', 'ALIPAY_SANDBOX': 'true'}))
        self.adapter = AlipayProvider()
        self.order = SimpleNamespace(order_id='a' * 32, amount=123, plan_id='pro', app_id='test-app', merchant_id='test-seller')

    def body(self, **updates):
        values = dict(out_trade_no='a'*32, trade_no='test-transaction', total_amount='1.23',
                      app_id='test-app', seller_id='test-seller', trade_status='TRADE_SUCCESS')
        values.update(updates)
        content = '&'.join(f'{k}={v}' for k, v in sorted(values.items()))
        return urlencode({**values, 'sign_type': 'RSA2', 'sign': sign_with_rsa2(self.private, content, 'utf-8')}).encode()

    async def test_signed_notification_and_tampering(self):
        fact = await self.adapter.verify_notification(self.body(), {})
        self.assertEqual((fact.status, fact.amount, fact.merchant_id), ('paid', 123, 'test-seller'))
        for body in (self.body().replace(b'1.23', b'1.24'), self.body()+b'&total_amount=0.01', b'sign=forged'):
            with self.assertRaisesRegex(EntitlementError, 'PAYMENT_SIGNATURE_INVALID'):
                await self.adapter.verify_notification(body, {})

    async def test_signed_wrong_merchant_app_or_state_rejected(self):
        for update in ({'seller_id':'other'}, {'app_id':'other'}, {'trade_status':'REFUND'}, {'trans_currency':'USD'}):
            with self.assertRaises(EntitlementError):
                await self.adapter.verify_notification(self.body(**update), {})

    async def test_official_page_sdk_builds_sandbox_redirect(self):
        result = await self.adapter.create_order(self.order)
        url = urlsplit(result['redirect_url'])
        self.assertEqual(url.hostname, 'openapi-sandbox.dl.alipaydev.com')
        params = parse_qs(url.query)
        self.assertEqual(params['method'], ['alipay.trade.page.pay'])
        self.assertEqual(json.loads(params['biz_content'][0])['total_amount'], '1.23')
        self.assertNotIn('seller_id', json.loads(params['biz_content'][0]))
        self.assertTrue(params['sign'][0])

    async def test_official_query_sdk_verifies_response(self):
        payload = json.dumps({'code':'10000', 'out_trade_no':'a'*32, 'trade_no':'test-tx',
                              'trade_status':'TRADE_SUCCESS', 'total_amount':'1.23'}, separators=(',', ':'))
        signed = ('{"alipay_trade_query_response":' + payload + ',"sign":"' +
                  sign_with_rsa2(self.private, payload, 'utf-8') + '"}').encode()
        with patch('alipay.aop.api.DefaultAlipayClient.do_post', return_value=signed):
            with self.assertRaisesRegex(EntitlementError, 'PAYMENT_QUERY_IDENTITY_UNVERIFIED'):
                await self.adapter.query_order(self.order)
        with patch('alipay.aop.api.DefaultAlipayClient.do_post', return_value=signed.replace(b'1.23', b'1.24')):
            with self.assertRaisesRegex(EntitlementError, 'ALIPAY_QUERY_FAILED'):
                await self.adapter.query_order(self.order)

    async def test_query_rejects_changed_local_merchant_before_request(self):
        self.order.merchant_id = 'other'
        with patch.object(self.adapter.client, 'execute') as execute:
            with self.assertRaisesRegex(EntitlementError, 'PAYMENT_MERCHANT_CHANGED'):
                await self.adapter.query_order(self.order)
            execute.assert_not_called()

    def test_integer_minor_units(self):
        self.assertEqual(fen('19.90'), 1990)
        for value in ('0.001', 'NaN', 'Infinity', '-1', 'bad'):
            with self.assertRaises(EntitlementError):
                fen(value)


class WechatAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_body_and_signature_headers_survive_internal_transport(self):
        raw = b'{ "resource": "signed original bytes" }\n'
        async def handle(request):
            self.assertEqual(request.content, raw)
            self.assertEqual(request.headers['wechatpay-signature'], 'test-signature')
            self.assertEqual(request.headers['authorization'], 'Bearer internal-test')
            self.assertNotIn('x-shenzhi-user-id', request.headers)
            return httpx.Response(200, json=dict(order_id='a'*32, transaction_id='test', amount=123, currency='CNY',
                merchant_id='test-merchant', app_id='test-app', status='paid'))
        real_client = httpx.AsyncClient
        with patch.dict(os.environ, {'WECHAT_APP_ID':'test-app', 'WECHAT_MCH_ID':'test-merchant',
                                    'PAYMENT_SERVICE_URL':'http://payment.test', 'PAYMENT_SERVICE_TOKEN':'internal-test'}), patch(
                'app.integrations.payment.wechat.httpx.AsyncClient', side_effect=lambda **kwargs:
                real_client(**kwargs, transport=httpx.MockTransport(handle))):
            fact = await WechatPayProvider().verify_notification(raw, {'wechatpay-signature':'test-signature', 'x-shenzhi-user-id':'untrusted'})
            self.assertEqual(fact.amount, 123)

    def test_mock_requires_both_explicit_switches_and_development(self):
        for env in ({'ENVIRONMENT':'production', 'BILLING_MOCK_ENABLED':'true'},
                    {'ENVIRONMENT':'development', 'BILLING_MOCK_ENABLED':'false'}):
            with patch.dict(os.environ, {**env, 'BILLING_PAYMENT_MODE':'mock'}), self.assertRaises(EntitlementError):
                provider('wechat')
