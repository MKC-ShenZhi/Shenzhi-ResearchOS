"""Membership purchase, renewal and entitlement protection on real PostgreSQL."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from tests import test_billing_postgres as fixtures
from app.models.agent_entitlements import OwnerEntitlementRow
from app.models.billing import BillingOrderRow
from app.schemas.billing import CreateOrder, ExpectedQuote
from app.services.billing import service
from app.services.agent_entitlements.service import EntitlementError, now_utc


class UpgradeQuoteMathTests(unittest.TestCase):
    def test_catalog_and_remaining_value_rounding(self):
        self.assertEqual([service.CATALOG[key]['amount'] for key in ('basic', 'pro', 'research')], [0, 1990, 4990])
        end = datetime(2028, 3, 1, tzinfo=timezone.utc)
        owner = SimpleNamespace(plan_id='pro', policy_revision='pro-v1', enabled=True, source='admin', expires_at=end)
        start = service.add_calendar_months(end, -1)
        halfway = start + (end - start) / 2
        for at, expected in ((start, 3000), (halfway, 1500), (end - timedelta(microseconds=1), 1),
                             (service.add_calendar_months(end, -2), 6000)):
            quoted = service.upgrade_quote('test', owner, 'research-v1', at)
            self.assertEqual(quoted['amount'], expected)
            self.assertEqual(quoted['subscription_expires_at'], end.isoformat())

    def test_quote_bound_to_owner_and_target_revision(self):
        at = datetime(2028, 1, 31, tzinfo=timezone.utc)
        owner = SimpleNamespace(plan_id='pro', policy_revision='pro-v1', enabled=True, source='admin',
                                expires_at=at + timedelta(days=10))
        original = service.upgrade_quote('test', owner, 'research-v1', at)
        self.assertNotEqual(original['quote_token'], service.upgrade_quote('other', owner, 'research-v1', at)['quote_token'])
        self.assertNotEqual(original['quote_token'], service.upgrade_quote('test', owner, 'research-v2', at)['quote_token'])
        with self.assertRaisesRegex(EntitlementError, 'QUOTE_INVALID'):
            service.upgrade_quote('test', owner, 'research-v1', at.replace(tzinfo=None))


@unittest.skipUnless(fixtures.URL, 'BILLING_TEST_DATABASE_URL not selected')
class MembershipTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.BillingPostgresTests.asyncSetUp
    asyncTearDown = fixtures.BillingPostgresTests.asyncTearDown
    migrate = staticmethod(fixtures.BillingPostgresTests.migrate)
    scope = fixtures.BillingPostgresTests.scope
    publish = fixtures.BillingPostgresTests.publish
    create = fixtures.BillingPostgresTests.create
    paid = fixtures.BillingPostgresTests.paid
    assign = fixtures.BillingPostgresTests.assign

    async def test_basic_registration_can_purchase_and_owner_change_is_preserved(self):
        from app.services.agent_entitlements.defaults import initialize_free
        async with self.scope() as db:
            self.assertEqual(await initialize_free(db, 'test'), 1)
        order = await self.create()
        self.assertEqual((await service.mock_pay('test', order['order_id']))['fulfillment_status'], 'completed')
        order = await self.create()
        await self.assign('basic')
        paid = await service.mock_pay('test', order['order_id'])
        self.assertEqual((paid['payment_status'], paid['fulfillment_error']), ('paid', 'ENTITLEMENT_CHANGED'))
        with self.assertRaisesRegex(EntitlementError, 'PAID_ORDER_REQUIRES_FULFILLMENT'):
            await self.create()

    async def test_basic_free_and_legacy_paid_plan_protected(self):
        self.assertEqual(service.CATALOG['basic']['amount'], 0)
        with self.assertRaisesRegex(EntitlementError, 'PLAN_NOT_PURCHASABLE'):
            await self.create('basic')
        async with self.scope() as db:
            await service.assign_policy(db, None, 'user:test', 'pro', 'pro-v1-test')
        for plan in ('pro', 'research'):
            with self.assertRaisesRegex(EntitlementError, 'LEGACY_PERMANENT_ENTITLEMENT_REQUIRES_ADMIN'):
                await self.create(plan)

    async def test_admin_gift_renewal_uses_calendar_month_and_is_idempotent(self):
        from app.services.agent_entitlements.dates import add_calendar_months
        for plan in ('pro', 'research'):
            await self.assign(plan)
            before = datetime.fromisoformat((await service.subscription('test'))['expires_at'])
            order = await self.create(plan)
            paid = await service.mock_pay('test', order['order_id'])
            self.assertEqual(datetime.fromisoformat(paid['subscription_expires_at']), add_calendar_months(before, 1))
            self.assertEqual((await service.mock_pay('test', order['order_id']))['subscription_expires_at'], paid['subscription_expires_at'])

    async def test_pending_purchase_ignores_old_quote_expiry(self):
        first = await self.create()
        async with self.scope() as db:
            row = await db.get(BillingOrderRow, first['order_id'])
            self.assertNotIn('quoted_at', row.snapshot)
            self.assertNotIn('quote_expires_at', row.snapshot)
            row.snapshot = {**row.snapshot, 'quote_expires_at': (now_utc()-timedelta(days=1)).isoformat()}
        self.assertEqual((await self.create())['order_id'], first['order_id'])
        self.assertEqual((await service.prepare_payment('test', first['order_id']))['payment_status'], 'pending')
        self.assertEqual((await service.mock_pay('test', first['order_id']))['fulfillment_status'], 'completed')

    async def test_renewal_ignores_old_quote_expiry_and_missing_legacy_action(self):
        await self.assign('pro')
        order = await self.create()
        async with self.scope() as db:
            row = await db.get(BillingOrderRow, order['order_id'])
            row.snapshot = {key: value for key, value in row.snapshot.items() if key != 'action'}
            row.snapshot = {**row.snapshot, 'quote_expires_at': (now_utc() - timedelta(days=1)).isoformat()}
        self.assertEqual((await self.create())['order_id'], order['order_id'])
        self.assertEqual((await service.prepare_payment('test', order['order_id']))['payment_status'], 'pending')
        self.assertEqual((await service.mock_pay('test', order['order_id']))['fulfillment_status'], 'completed')

    async def test_billing_pro_can_upgrade_and_expired_quote_cannot_become_purchase(self):
        await self.paid()
        quoted = await service.quote('test', 'research')
        # The quote has become invalid because the account no longer has Pro.
        await self.assign('basic')
        with self.assertRaisesRegex(EntitlementError, 'UPGRADE_NOT_AVAILABLE'):
            await self.upgrade(quoted)
        self.assertEqual(len((await service.list_orders('test'))['items']), 1)
        await self.paid()
        quoted = await service.quote('test', 'research')
        order = await self.upgrade(quoted)
        result = await service.mock_pay('test', order['order_id'])
        self.assertEqual(result['fulfillment_status'], 'completed')
        self.assertEqual(result['subscription_expires_at'], quoted['subscription_expires_at'])

    async def test_legacy_order_keeps_thirty_day_duration(self):
        order = await self.create()
        async with self.scope() as db:
            row = await db.get(BillingOrderRow, order['order_id'])
            row.snapshot = {'duration_days': 30}
        at = datetime(2026, 1, 31, tzinfo=timezone.utc)
        with patch.object(service, 'now_utc', return_value=at):
            paid = await service.mock_pay('test', order['order_id'])
        self.assertEqual(datetime.fromisoformat(paid['subscription_expires_at']), at + timedelta(days=30))

    async def test_purchase_month_end_and_late_renewal_start_at_fulfillment(self):
        from app.services.agent_entitlements.dates import add_calendar_months
        order = await self.create()
        at = datetime(2028, 1, 31, 12, tzinfo=timezone.utc)
        with patch.object(service, 'now_utc', return_value=at):
            paid = await service.mock_pay('test', order['order_id'])
        self.assertEqual(datetime.fromisoformat(paid['subscription_expires_at']), add_calendar_months(at, 1))
        await self.assign('pro')
        order = await self.create()
        later = datetime.fromisoformat((await service.subscription('test'))['expires_at']) + timedelta(days=2)
        with patch.object(service, 'now_utc', return_value=later):
            paid = await service.mock_pay('test', order['order_id'])
        self.assertEqual(datetime.fromisoformat(paid['subscription_expires_at']), add_calendar_months(later, 1))

    async def upgrade(self, quoted=None):
        quoted = quoted or await service.quote('test', 'research')
        return await service.create_order('test', CreateOrder(plan_id='research', channel='alipay',
            expected_quote=ExpectedQuote(quoted_at=quoted['quoted_at'], quote_token=quoted['quote_token'])))

    async def test_upgrade_quote_http_contract_and_success(self):
        await self.assign('pro')
        before = await service.subscription('test')
        response = await self.browser.post('/api/v1/billing/quote', json={'plan_id': 'research'})
        self.assertEqual(response.status_code, 200, response.text)
        quoted = response.json()['data']
        self.assertGreater(quoted['amount'], 0)
        self.assertLessEqual(quoted['amount'], 3000)
        response = await self.browser.post('/api/v1/billing/orders', json={
            'plan_id': 'research', 'channel': 'alipay',
            'expected_quote': {key: quoted[key] for key in ('quoted_at', 'quote_token')}})
        self.assertEqual(response.status_code, 200, response.text)
        order = response.json()['data']
        self.assertEqual((order['action'], order['amount']), ('upgrade', quoted['amount']))
        self.assertEqual((await service.mock_pay('test', order['order_id']))['fulfillment_status'], 'completed')
        after = await service.subscription('test')
        self.assertEqual((after['plan_id'], after['expires_at']), ('research', before['expires_at']))
        self.assertEqual(after['policy_revision'], 'research-v1-test')
        self.assertEqual((await service.mock_pay('test', order['order_id']))['subscription_expires_at'], before['expires_at'])
        with self.assertRaisesRegex(EntitlementError, 'PLAN_CHANGE_NOT_SUPPORTED'):
            await self.create('pro')

    async def test_upgrade_quote_required_tampered_expired_and_new_quote(self):
        await self.assign('pro')
        with self.assertRaisesRegex(EntitlementError, 'QUOTE_REQUIRED'):
            await self.create('research')
        quoted = await service.quote('test', 'research')
        with self.assertRaisesRegex(EntitlementError, 'QUOTE_CHANGED'):
            await self.upgrade({**quoted, 'quote_token': 'forged'})
        later = datetime.fromisoformat(quoted['quote_expires_at']) + timedelta(seconds=1)
        with patch.object(service, 'now_utc', return_value=later):
            with self.assertRaisesRegex(EntitlementError, 'QUOTE_EXPIRED'):
                await self.upgrade(quoted)
            fresh = await service.quote('test', 'research')
            self.assertGreater(fresh['quoted_at'], quoted['quoted_at'])
            order = await self.upgrade(fresh)
        self.assertEqual(order['amount'], fresh['amount'])

    async def test_expired_upgrade_order_allows_new_quote_and_renewal(self):
        await self.assign('pro')
        first = await self.upgrade()
        later = datetime.fromisoformat(first['quote_expires_at']) + timedelta(seconds=1)
        with patch.object(service, 'now_utc', return_value=later):
            with self.assertRaisesRegex(EntitlementError, 'QUOTE_EXPIRED'):
                await service.prepare_payment('test', first['order_id'])
            second = await self.upgrade()
            self.assertNotEqual(first['order_id'], second['order_id'])
            self.assertEqual((await service.get_order('test', first['order_id']))['payment_status'], 'closed')
        later = datetime.fromisoformat(second['quote_expires_at']) + timedelta(seconds=1)
        with patch.object(service, 'now_utc', return_value=later):
            renewal = await self.create()
            self.assertEqual(renewal['action'], 'renew')
            self.assertEqual((await service.mock_pay('test', renewal['order_id']))['fulfillment_status'], 'completed')
        # Closed local checkouts still accept verified delayed channel payments.
        async with self.scope() as db:
            row = await db.get(BillingOrderRow, second['order_id'])
            from app.integrations.payment.base import provider
            fact = provider(row.channel).success(row)
        await service.confirm('alipay', 'mock', fact)
        paid = await service.get_order('test', second['order_id'])
        self.assertEqual((paid['payment_status'], paid['fulfillment_error']), ('paid', 'ENTITLEMENT_CHANGED'))

    async def test_paid_upgrade_drain_retry_after_quote_expiry_keeps_usage_and_revision(self):
        from sqlalchemy import select
        from app.models.agent_entitlements import WindowCounterRow, GrantRootRow
        await self.assign('pro')
        quoted = await service.quote('test', 'research')
        order = await self.upgrade(quoted)
        grant, _ = await fixtures.BillingPostgresTests.grant(self)
        async with self.scope() as db:
            counter = await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))
            counter.used = 123
        paid = await service.mock_pay('test', order['order_id'])
        self.assertEqual((paid['payment_status'], paid['fulfillment_error']), ('paid', 'ACTIVE_GRANTS_REQUIRE_DRAIN'))
        with self.assertRaisesRegex(EntitlementError, 'PAID_ORDER_REQUIRES_FULFILLMENT'):
            await self.upgrade(quoted)
        async with self.scope() as db:
            (await db.get(GrantRootRow, grant.grant_id)).status = 'closed'
        await self.publish('new')
        later = datetime.fromisoformat(order['quote_expires_at']) + timedelta(seconds=1)
        with patch.object(service, 'now_utc', return_value=later):
            result = await service.refresh('test', order['order_id'])
        self.assertEqual(result['fulfillment_status'], 'completed')
        async with self.scope() as db:
            self.assertEqual((await db.get(OwnerEntitlementRow, 'user:test')).policy_revision, 'research-v1-test')
            self.assertEqual((await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))).used, 123)
            from app.models.agent_entitlements import EntitlementPolicyRow
            from app.services.agent_entitlements.policy import EntitlementPolicy
            from app.services.agent_entitlements.admin import daily_balance
            policy = EntitlementPolicy.model_validate((await db.get(EntitlementPolicyRow, 'research-v1-test')).payload)
            self.assertEqual(policy.rules[0].limit_units, 3000000)
            window = policy.rules[0].window('user:test', policy.policy_revision, now_utc())
            self.assertEqual(await daily_balance(db, 'user:test', window), (123, 0))

    async def test_upgrade_owner_change_and_expiry_preserve_payment(self):
        await self.assign('pro')
        order = await self.upgrade()
        await self.assign('research')
        before = await service.subscription('test')
        result = await service.mock_pay('test', order['order_id'])
        self.assertEqual((result['payment_status'], result['fulfillment_error']), ('paid', 'ENTITLEMENT_CHANGED'))
        self.assertEqual(await service.subscription('test'), before)

    async def test_upgrade_concurrent_checkout_and_notifications(self):
        import asyncio
        from sqlalchemy import func, select
        from app.models.agent_entitlements import EntitlementAuditRow
        await self.assign('pro')
        quoted = await service.quote('test', 'research')
        results = await asyncio.gather(*(self.upgrade(quoted) for _ in range(4)))
        self.assertEqual(len({row['order_id'] for row in results}), 1)
        await asyncio.gather(*(service.mock_pay('test', results[0]['order_id']) for _ in range(4)))
        async with self.scope() as db:
            count = await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(EntitlementAuditRow.principal == 'billing'))
        self.assertEqual(count, 1)

    async def test_live_upgrade_signed_notification(self):
        await self.assign('pro')
        before = await service.subscription('test')
        await fixtures.BillingPostgresTests.assert_live_alipay_signed_callback(self, 'research')
        after = await service.subscription('test')
        self.assertEqual((after['plan_id'], after['expires_at']), ('research', before['expires_at']))

    async def test_paid_upgrade_cannot_extend_expired_term(self):
        await self.assign('pro')
        order = await self.upgrade()
        expiry = datetime.fromisoformat((await service.subscription('test'))['expires_at'])
        with patch.object(service, 'now_utc', return_value=expiry + timedelta(seconds=1)):
            result = await service.mock_pay('test', order['order_id'])
        self.assertEqual((result['payment_status'], result['fulfillment_status'], result['fulfillment_error']),
                         ('paid', 'pending', 'UPGRADE_NOT_AVAILABLE'))
        async with self.scope() as db:
            self.assertEqual((await db.get(OwnerEntitlementRow, 'user:test')).expires_at, expiry)

    async def test_legacy_upgrade_without_snapshot_is_preserved(self):
        order = await self.create()
        async with self.scope() as db:
            row = await db.get(BillingOrderRow, order['order_id'])
            row.snapshot = {**row.snapshot, 'action': 'upgrade'}
        with self.assertRaisesRegex(EntitlementError, 'QUOTE_SNAPSHOT_INVALID'):
            await service.prepare_payment('test', order['order_id'])
        result = await service.mock_pay('test', order['order_id'])
        self.assertEqual((result['payment_status'], result['fulfillment_error']), ('paid', 'QUOTE_SNAPSHOT_INVALID'))

    async def test_upgrade_exception_retains_paid_order_and_rolls_back(self):
        await self.assign('pro')
        order = await self.upgrade()
        before = await service.subscription('test')
        original = service.assign_policy
        async def fail(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError('simulated fulfillment crash')
        with patch.object(service, 'assign_policy', fail), self.assertRaises(RuntimeError):
            await service.mock_pay('test', order['order_id'])
        self.assertEqual((await service.get_order('test', order['order_id']))['payment_status'], 'paid')
        self.assertEqual(await service.subscription('test'), before)
        self.assertEqual((await service.refresh('test', order['order_id']))['fulfillment_status'], 'completed')

    async def test_concurrent_registration_and_purchase_do_not_overwrite(self):
        import asyncio
        from app.services.agent_entitlements.defaults import initialize_free
        async def initialize():
            async with self.scope() as db:
                return await initialize_free(db, 'test')
        order, _ = await asyncio.wait_for(asyncio.gather(self.create(), initialize()), 10)
        paid = await service.mock_pay('test', order['order_id'])
        actual = await service.subscription('test')
        if paid['fulfillment_status'] == 'completed':
            self.assertEqual(actual['plan_id'], 'pro')
        else:
            # Registration can commit after checkout. Preserve the new assignment
            # rather than bypassing the same snapshot check used for Admin edits.
            self.assertEqual((paid['payment_status'], paid['fulfillment_error']), ('paid', 'ENTITLEMENT_CHANGED'))
            self.assertEqual((actual['plan_id'], actual['source']), ('basic', 'registration'))

    async def test_upgrade_request_never_silently_becomes_full_price_purchase(self):
        response = await self.browser.post('/api/v1/billing/orders', json={
            'plan_id': 'pro', 'channel': 'alipay', 'expected_quote': {'quoted_at': now_utc().isoformat(), 'quote_token': 'old'}})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn('UPGRADE_NOT_AVAILABLE', response.text)
        self.assertEqual((await service.list_orders('test'))['items'], [])
