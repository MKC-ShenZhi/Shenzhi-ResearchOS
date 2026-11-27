"""Opt-in real SQL/locks. Only random schemas in a local *_test DB are touched."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import uuid

import httpx
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from agent_contracts.canonical import digest
from agent_contracts.v2 import ModelIdentity, SkillIdentity, CallPermitRequest, PermitStart
from app.main import app
from app.models.agent_entitlements import (OwnerEntitlementRow, WindowCounterRow, GrantRootRow, EntitlementAuditRow)
from app.models.billing import BillingOrderRow
from app.schemas.admin_plans import PublishPlans, AssignPlans
from app.schemas.billing import CreateOrder
from app.services.agent_entitlements import admin
from app.services.agent_entitlements.plans import build
from app.services.agent_entitlements.dates import add_calendar_months
from app.services.agent_entitlements.service import Entitlements, EntitlementError, now_utc
from app.services.billing import service
from app.integrations.payment.base import provider

URL = os.getenv('BILLING_TEST_DATABASE_URL', '')


@unittest.skipUnless(URL, 'BILLING_TEST_DATABASE_URL not selected')
class BillingPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        parsed = urlsplit(URL)
        if parsed.hostname not in ('127.0.0.1', 'localhost') or not parsed.path.endswith('_test'):
            raise RuntimeError('Billing tests require an explicitly selected local *_test database')
        self.schema = 'billing_' + uuid.uuid4().hex
        self.engine = create_async_engine(URL.replace('postgresql://', 'postgresql+asyncpg://'),
            connect_args={'server_settings': {'search_path': self.schema}})
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await connection.run_sync(self.migrate)
            await connection.execute(text('CREATE TABLE "user" (id TEXT PRIMARY KEY, email TEXT)'))
            await connection.execute(text("INSERT INTO \"user\" VALUES ('test', 'test@example.test')"))
        self.enterContext(patch.dict(os.environ, {'ENVIRONMENT': 'test', 'BILLING_PAYMENT_MODE': 'mock',
            'BILLING_MOCK_ENABLED': 'true', 'BACKEND_BFF_SECRET': 'test-bff-secret'}))
        self.enterContext(patch.object(service, 'session_scope', self.scope))
        self.auth = {'x-shenzhi-bff-secret': 'test-bff-secret', 'x-shenzhi-user-id': 'test'}
        self.browser = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=self.auth)
        self.addAsyncCleanup(self.browser.aclose)
        self.entitlements = Entitlements(issuer='test', audience='agent-test', kid='test', private_key=Ed25519PrivateKey.generate())
        self.identity = ModelIdentity(schema_version=1, kind='model', capability_id='model:test/m1', provider_id='test',
            registry_model_id='test/m1', upstream_model='m1', configuration_release_digest=digest('test-config'), dependency_digests=[])
        skill = SkillIdentity(schema_version=1, kind='skill', capability_id='skill:deep-research',
            resource_content_digest=digest('test-skill'), dependency_digests=[])
        self.catalog = {'capabilities': [{'identity': i.model_dump(mode='json'), 'version': digest(i.model_dump(mode='json'))}
                                         for i in (self.identity, skill)]}
        await self.publish('test')

    @staticmethod
    def migrate(connection, names=('027_agent_entitlements', '028_formal_plans', '029_billing'), action='upgrade'):
        for name in names:
            path = Path(__file__).resolve().parents[1] / 'migrations/versions' / (name + '.py')
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(connection)):
                getattr(module, action)()

    @asynccontextmanager
    async def scope(self):
        async with self.factory() as db, db.begin():
            yield db

    async def asyncTearDown(self):
        async with self.engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await self.engine.dispose()

    async def publish(self, release):
        bundle = build(self.catalog, release=release, model_budgets={'model:test/m1': dict(schema_version=1,
            input_basis='risk_assessed_utf8_v1', input_overhead_tokens=5, context_window_tokens=100,
            max_output_tokens=15, output_limit_semantics='completion_including_reasoning')}, risk_profile='test-risk')
        async with self.scope() as db:
            await admin.publish(db, PublishPlans(**bundle, operation_id='publish-' + release, reason='test',
                approval_ref='test-review', risk_approval_ref='test-risk-review'), 'local-admin:test',
                {'models': [{'value': 'test/m1', 'enabled': True}], 'skills': [{'name': 'deep-research'}]})

    async def create(self, plan='pro'):
        return await service.create_order('test', CreateOrder(plan_id=plan, channel='wechat'))

    async def paid(self, plan='pro'):
        order = await self.create(plan)
        return await service.mock_pay('test', order['order_id'])

    async def assign(self, plan='basic', action='assign'):
        async with self.scope() as db:
            return await admin.assign(db, AssignPlans(operation_id=uuid.uuid4().hex, reason='test', user_ids=['test'],
                action=action, duration_months=1 if action == 'assign' and plan != 'basic' else None, plan_id=plan if action == 'assign' else None,
                policy_revision=plan + '-v1-test' if action == 'assign' else None, preview=False), 'local-admin:test')

    async def grant(self):
        async with self.scope() as db:
            submission, grant = await self.entitlements.authorize_submission(db, owner_id='user:test', client_key=uuid.uuid4().hex,
                request={'owner_id': 'user:test', 'prompt': 'test', 'model': 'test/m1', 'skills': []})
            receipt = await self.entitlements.bind_grant(db, grant_id=grant.grant_id, task_id=uuid.uuid4().hex,
                owner_id='user:test', submission_id=submission.submission_id, request_digest=grant.request_digest,
                expected_revision=1, expected_binding_revision=0)
        return grant, receipt

    def request(self, grant, receipt, call='call'):
        return CallPermitRequest(schema_version=1, call_id=call, logical_call_id=call, request_digest=digest(call),
            grant_id=grant.grant_id, grant_revision=1, reservation_id=grant.reservation_id, binding_receipt_id=receipt.receipt_id,
            owner_id='user:test', submission_id=grant.submission_id, task_id=receipt.bound_task_id, run_id='run',
            execution_id='execution', control_attestation_id='attestation', capability_id=self.identity.capability_id,
            capability_version=digest(self.identity.model_dump(mode='json')), invocation_mode='internal', purpose='main',
            requested_allocations=[dict(schema_version=1, allocation_id=a.allocation_id, metric=a.metric, unit=a.unit, upper_bound_units=20)
                                   for a in grant.allocations if a.unit == 'token'],
            input_bound_evidence_ref=None, output_bound_evidence_ref=None, risk_profile='test-risk',
            model_budget=dict(schema_version=1, basis='risk_assessed_utf8_v1', input_bytes=0, requested_output_tokens=15,
                              model_max_output_tokens=15, model_context_window=100))

    async def test_http_mock_purchase_entitlement_renewal_and_ownership(self):
        response = await self.browser.post('/api/v1/billing/orders', json={'plan_id': 'pro', 'channel': 'wechat'})
        self.assertEqual(response.status_code, 200, response.text)
        order = response.json()['data']
        url = '/api/v1/billing/orders/' + order['order_id']
        self.assertEqual((await self.browser.get(url, headers={'x-shenzhi-user-id': 'other'})).status_code, 404)
        paid = await self.browser.post(url + '/mock-pay')
        self.assertEqual(paid.json()['data']['fulfillment_status'], 'completed', paid.text)
        subscription = (await self.browser.get('/api/v1/billing/subscription')).json()['data']
        self.assertEqual((subscription['plan_id'], subscription['status']), ('pro', 'active'))
        grant, _ = await self.grant()
        self.assertEqual(grant.policy_revision, 'pro-v1-test')
        async with self.scope() as db:
            counter = await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))
            counter.used = 123
        await self.browser.post(url + '/mock-pay')
        self.assertEqual((await service.subscription('test'))['expires_at'], subscription['expires_at'])
        await self.paid()
        from datetime import datetime
        extended = datetime.fromisoformat((await service.subscription('test'))['expires_at'])
        self.assertEqual(extended, add_calendar_months(datetime.fromisoformat(subscription['expires_at']), 1))
        async with self.scope() as db:
            self.assertEqual((await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))).used, 123)

    async def test_active_grant_blocks_switch_and_paid_retry_is_safe(self):
        await self.assign()
        grant, _ = await self.grant()
        async with self.scope() as db:
            (await db.get(OwnerEntitlementRow, 'user:test')).expires_at = now_utc() - timedelta(seconds=1)
            counter = await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))
            counter.used = 77
        with self.assertRaisesRegex(EntitlementError, 'ACTIVE_GRANTS_REQUIRE_DRAIN'):
            await self.create()
        async with self.scope() as db:
            self.assertEqual((await db.get(OwnerEntitlementRow, 'user:test')).plan_id, 'basic')
            (await db.get(GrantRootRow, grant.grant_id)).status = 'closed'  # Test fixture models a completed drain.
        self.assertEqual((await self.paid())['fulfillment_status'], 'completed')
        async with self.scope() as db:
            self.assertEqual((await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))).used, 77)

    async def test_concurrent_duplicate_and_sequential_renewals(self):
        first = await self.create()
        await asyncio.gather(*(service.mock_pay('test', first['order_id']) for _ in range(5)))
        before = (await service.subscription('test'))['expires_at']
        for _ in range(2):
            await self.paid()
        from datetime import datetime
        after = (await service.subscription('test'))['expires_at']
        self.assertEqual(datetime.fromisoformat(after), add_calendar_months(add_calendar_months(datetime.fromisoformat(before), 1), 1))
        async with self.scope() as db:
            count = await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(EntitlementAuditRow.principal == 'billing'))
            self.assertEqual(count, 3)

    async def test_unfinished_orders_block_other_plans_and_reuse_checkout(self):
        first = await self.create()
        again = await service.create_order('test', CreateOrder(plan_id='pro', channel='alipay'))
        self.assertEqual((again['order_id'], again['channel']), (first['order_id'], 'wechat'))
        response = await self.browser.post('/api/v1/billing/orders', json={'plan_id': 'research', 'channel': 'wechat'})
        self.assertEqual(response.status_code, 409)
        self.assertIn('UNFINISHED_ORDER_PLAN_CONFLICT', response.text)
        other = await service.create_order('other', CreateOrder(plan_id='research', channel='wechat'))
        self.assertNotEqual(other['order_id'], first['order_id'])
        with patch.object(service, 'assign_policy', side_effect=EntitlementError('TEST_PENDING')):
            paid = await service.mock_pay('test', first['order_id'])
        self.assertEqual((paid['payment_status'], paid['fulfillment_status']), ('paid', 'pending'))
        with self.assertRaisesRegex(EntitlementError, 'UNFINISHED_ORDER_PLAN_CONFLICT'):
            await self.create('research')
        self.assertEqual((await service.get_order('test', first['order_id']))['payment_status'], 'paid')
        self.assertEqual((await service.refresh('test', first['order_id']))['fulfillment_status'], 'completed')

    async def test_mock_paid_pending_cannot_fulfill_after_production_switch(self):
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            created = await self.create()
            with patch.object(service, 'assign_policy', side_effect=EntitlementError('TEST_PENDING')):
                order = await service.mock_pay('test', created['order_id'])
        for env in ({'ENVIRONMENT': 'production'}, {'BILLING_MOCK_ENABLED': 'false'}, {'BILLING_PAYMENT_MODE': 'live'}):
            with patch.dict(os.environ, env):
                result = await service.refresh('test', order['order_id'])
                await service.fulfill(order['order_id'])  # The common retry boundary is protected too.
            self.assertEqual((result['payment_status'], result['fulfillment_status']), ('paid', 'pending'))
            self.assertEqual(result['fulfillment_error'], 'MOCK_PAYMENT_DISABLED')
            self.assertEqual((await service.subscription('test'))['status'], 'unassigned')
            async with self.scope() as db:
                self.assertEqual(await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(
                    EntitlementAuditRow.principal == 'billing')), 0)
        self.assertEqual((await service.refresh('test', order['order_id']))['fulfillment_status'], 'completed')

    async def test_expiry_denies_submission_permit_start_but_allows_history(self):
        await self.paid()
        grant, receipt = await self.grant()
        request = self.request(grant, receipt)
        async with self.scope() as db:
            permit = await self.entitlements.permit(db, request)
            self.assertEqual(permit['decision'], 'authorized', permit)
        async with self.scope() as db:
            (await db.get(OwnerEntitlementRow, 'user:test')).expires_at = now_utc() - timedelta(seconds=1)
        self.assertEqual((await service.subscription('test'))['status'], 'expired')
        async with self.scope() as db:
            with self.assertRaises(EntitlementError):
                await self.entitlements.authorize_submission(db, owner_id='user:test', client_key='expired', request={})
            result = await self.entitlements.permit(db, self.request(grant, receipt, 'after-expiry'))
            self.assertEqual(result['decision'], 'denied')
            with self.assertRaises(EntitlementError):
                await self.entitlements.start(db, permit['permit']['permit_id'], PermitStart(schema_version=1,
                    start_operation_id='start', execution_id='execution', control_attestation_id='attestation'))
            # Settlement's lock_grant path must remain accessible after expiry.
            owner, root, history = await self.entitlements.lock_grant(db, grant.grant_id)
            self.assertEqual(history.grant_id, grant.grant_id)

    async def test_manual_assignment_and_plan_change_restrictions(self):
        await self.assign('pro')
        self.assertEqual((await self.paid())['action'], 'renew')
        with self.assertRaisesRegex(EntitlementError, 'QUOTE_REQUIRED'):
            await self.create('research')
        await self.assign('research')
        with self.assertRaisesRegex(EntitlementError, 'PLAN_CHANGE_NOT_SUPPORTED'):
            await self.create('pro')
        await self.assign(action='disable')
        with self.assertRaisesRegex(EntitlementError, 'ENTITLEMENT_DISABLED'):
            await self.create('research')

    async def test_amount_currency_merchant_and_channel_mismatch_never_pay(self):
        created = await self.create()
        async with self.scope() as db:
            order = await db.get(BillingOrderRow, created['order_id'])
            fact = provider('wechat').success(order)
        for values in ({'amount': 1}, {'currency': 'USD'}, {'merchant_id': 'other'}, {'app_id': 'other'}):
            with self.assertRaisesRegex(EntitlementError, 'PAYMENT_FACT_MISMATCH'):
                await service.confirm('wechat', 'mock', replace(fact, **values))
        with self.assertRaisesRegex(EntitlementError, 'PAYMENT_FACT_MISMATCH'):
            await service.confirm('alipay', 'mock', fact)
        self.assertEqual((await service.get_order('test', order.order_id))['payment_status'], 'pending')

    async def test_policy_snapshot_survives_new_publication(self):
        order = await self.create()
        await self.publish('new-release')
        result = await service.mock_pay('test', order['order_id'])
        self.assertEqual(result['fulfillment_status'], 'completed')
        async with self.scope() as db:
            self.assertEqual((await db.get(OwnerEntitlementRow, 'user:test')).policy_revision, 'pro-v1-test')

    async def test_fulfillment_exception_preserves_payment_and_rolls_back_entitlement(self):
        order = await self.create()
        original = service.assign_policy
        async def fail_after_assignment(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError('test simulated crash')
        with patch.object(service, 'assign_policy', fail_after_assignment), self.assertRaises(RuntimeError):
            await service.mock_pay('test', order['order_id'])
        result = await service.get_order('test', order['order_id'])
        self.assertEqual((result['payment_status'], result['fulfillment_status']), ('paid', 'pending'))
        self.assertEqual((await service.subscription('test'))['status'], 'unassigned')
        self.assertEqual((await service.refresh('test', order['order_id']))['fulfillment_status'], 'completed')

    async def test_migration_keeps_permanent_admin_grants(self):
        async with self.scope() as db:
            await service.assign_policy(db, None, 'user:test', 'research', 'research-v1-test')
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda c: self.migrate(c, ('029_billing',), 'downgrade'))
            await connection.run_sync(lambda c: self.migrate(c, ('029_billing',)))
        state = await service.subscription('test')
        self.assertEqual((state['status'], state['source'], state['expires_at']), ('active', 'admin', None))

    async def test_auth_amount_injection_and_mock_production_isolation(self):
        response = await self.browser.post('/api/v1/billing/orders', json={'plan_id': 'pro', 'channel': 'wechat', 'amount': 1})
        self.assertEqual(response.status_code, 422)
        self.assertEqual((await self.browser.get('/api/v1/billing/plans', headers={'x-shenzhi-bff-secret': 'wrong'})).status_code, 401)
        order = await self.create()
        for env in ({'ENVIRONMENT': 'production'}, {'BILLING_MOCK_ENABLED': 'false'}, {'BILLING_PAYMENT_MODE': 'live'}):
            with patch.dict(os.environ, env):
                self.assertNotEqual((await self.browser.post('/api/v1/billing/orders/' + order['order_id'] + '/mock-pay')).status_code, 200)

    async def test_authorized_start_deadline_is_capped_by_subscription(self):
        await self.paid()
        grant, receipt = await self.grant()
        expires = now_utc() + timedelta(seconds=30)
        async with self.scope() as db:
            (await db.get(OwnerEntitlementRow, 'user:test')).expires_at = expires
        async with self.scope() as db:
            permit = await self.entitlements.permit(db, self.request(grant, receipt))
            start = await self.entitlements.start(db, permit['permit']['permit_id'], PermitStart(schema_version=1,
                start_operation_id='start', execution_id='execution', control_attestation_id='attestation'))
            from datetime import datetime
            self.assertLessEqual(datetime.fromisoformat(start['start_before']), expires)

    async def test_live_alipay_signed_callback_uses_same_fulfillment(self):
        await self.assert_live_alipay_signed_callback()

    async def assert_live_alipay_signed_callback(self, plan='pro'):
        # Ephemeral official-SDK fixtures only: page signing and callback verification require no network.
        from tests.test_payment_providers import AlipayTests
        keys = AlipayTests()
        keys.setUp()
        self.addCleanup(keys.doCleanups)
        from urllib.parse import parse_qsl, urlencode
        from alipay.aop.api.util.SignatureUtils import get_sign_content, sign_with_rsa2
        with patch.dict(os.environ, {'ENVIRONMENT': 'production', 'BILLING_PAYMENT_MODE': 'live', 'BILLING_MOCK_ENABLED': 'false'}):
            quoted = await service.quote('test', plan) if plan == 'research' else None
            order = await service.create_order('test', CreateOrder(plan_id=plan, channel='alipay',
                expected_quote={key: quoted[key] for key in ('quoted_at', 'quote_token')} if quoted else None))
            payload = dict(parse_qsl(keys.body().decode()))
            amount = f"{order['amount'] // 100}.{order['amount'] % 100:02d}"
            payload.update(out_trade_no=order['order_id'], total_amount=amount)
            payload.pop('sign'); payload.pop('sign_type')
            signature = sign_with_rsa2(keys.private, get_sign_content(payload), 'utf-8')
            raw = urlencode({**payload, 'sign': signature, 'sign_type': 'RSA2'})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as callback:
                for _ in range(2):
                    response = await callback.post('/api/v1/payment-webhooks/alipay', content=raw,
                        headers={'content-type': 'application/x-www-form-urlencoded'})
                    self.assertEqual((response.status_code, response.text), (200, 'success'))
                forged = await callback.post('/api/v1/payment-webhooks/alipay', content=raw.replace('total_amount=' + amount, 'total_amount=0.03'))
                self.assertEqual(forged.status_code, 400)
            result = await service.get_order('test', order['order_id'])
            self.assertEqual((result['mode'], result['payment_status'], result['fulfillment_status']), ('live', 'paid', 'completed'))
            async with self.scope() as db:
                count = await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(EntitlementAuditRow.principal == 'billing'))
                self.assertEqual(count, 1)

    async def test_tunnel_and_local_admin_audits_are_both_visible(self):
        from app.models.agent_entitlements import EntitlementAuditRow
        from app.services.agent_entitlements.admin import list_audit
        async with self.factory() as db, db.begin():
            for principal in ['local-admin:legacy', 'ssh-admin:operator', 'system:billing']:
                db.add(EntitlementAuditRow(audit_id=str(uuid.uuid4()), operation_id=str(uuid.uuid4()),
                    principal=principal, reason='identity-test', payload={}, created_at=now_utc()))
        async with self.factory() as db:
            rows = await list_audit(db, page=1, page_size=100)
        principals = {row['principal'] for row in rows['items']}
        self.assertEqual(principals, {'local-admin:test', 'local-admin:legacy', 'ssh-admin:operator'})
