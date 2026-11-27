"""Purchased entitlements through real Agent Control, start and settlement SQL."""
from contextlib import asynccontextmanager
from datetime import timedelta
import os
import unittest
from unittest.mock import patch
from sqlalchemy import select
from tests import test_formal_plans as formal
from tests.integration import test_formal_plans_postgres as pg
from app.models.billing import BillingOrderRow
from app.models.agent_entitlements import OwnerEntitlementRow, WindowCounterRow
from app.schemas.billing import CreateOrder
from app.services.billing import service as billing
from app.services.agent_entitlements.service import EntitlementError, now_utc


@unittest.skipUnless(os.getenv('AGENT_A_LINE_TEST_DATABASE_URL') and os.getenv('BACKEND_A_LINE_TEST_DATABASE_URL'),
                     'two isolated PostgreSQL databases not selected')
class BillingExecutionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = formal.FormalPlanTests.asyncSetUp
    asyncTearDown = pg.FormalPostgresTests.asyncTearDown
    create_databases = pg.FormalPostgresTests.create_databases
    formal_setup = formal.FormalPlanTests.formal_setup
    prepare = formal.FormalPlanTests.prepare
    submit = formal.FormalPlanTests.submit
    bind = formal.FormalPlanTests.bind
    claim = formal.FormalPlanTests.claim
    start_call = formal.FormalPlanTests.start_call
    finish_call = formal.FormalPlanTests.finish_call
    ingest = formal.FormalPlanTests.ingest

    async def test_purchase_execution_expiry_and_historical_settlement(self):
        await self.formal_setup()
        async with self.backend() as db, db.begin():
            # An expired manual grant may be replaced; permanent grants stay protected.
            (await db.get(OwnerEntitlementRow, 'user:test')).expires_at = now_utc() - timedelta(seconds=1)
        @asynccontextmanager
        async def scope():
            async with self.backend() as db, db.begin():
                yield db
        with patch.object(billing, 'session_scope', scope), patch.dict(os.environ, {
                'ENVIRONMENT':'test', 'BILLING_PAYMENT_MODE':'mock', 'BILLING_MOCK_ENABLED':'true'}):
            order = await billing.create_order('test', CreateOrder(plan_id='pro', channel='wechat'))
            result = await billing.mock_pay('test', order['order_id'])
            self.assertEqual(result['fulfillment_status'], 'completed')
            self.policy = self.policies['pro']
            await self.prepare()
            await self.start_call('paid-call')
            async with self.backend() as db, db.begin():
                owner = await db.get(OwnerEntitlementRow, 'user:test')
                self.assertEqual((owner.plan_id, owner.source), ('pro', 'billing'))
                owner.expires_at = now_utc() - timedelta(seconds=1)
            with self.assertRaises(EntitlementError):
                await self.submit(key='expired-submission')
            async with self.backend() as db, db.begin():
                next_call = self.permit_request_value.model_copy(update={'call_id':'expired-call'})
                response = await self.service.permit(db, next_call)
                self.assertEqual(response['decision'], 'denied')
            # Already started Provider work completes after expiry and still settles.
            usage, _ = await self.finish_call()
            ack = await self.ingest(usage)
            self.assertEqual(ack.disposition, 'accepted')
            async with self.backend() as db:
                counter = await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))
                self.assertEqual((counter.used, counter.held), (10, 0))  # 7 prompt + 3 completion.
                order = await db.get(BillingOrderRow, order['order_id'])
                self.assertEqual(order.fulfillment_status, 'completed')
