"""Unit tests for configurable windows and production policy admission."""
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.models.agent_entitlements import EntitlementPolicyRow, OwnerEntitlementRow
from app.services.agent_entitlements.policy import EntitlementRule
from app.services.agent_entitlements.service import Entitlements, EntitlementError


def rule(**changes):
    values=dict(schema_version=1,rule_id='test-rule',metric='tokens',unit='token',capability_id=None,purpose='all',
        limit_units=100,reservation_units=20,call_upper_bound=10,accounting_basis='trusted_start',
        window_type='rolling',duration_seconds=18000,timezone=None,anchor=None)
    return EntitlementRule(**dict(values,**changes))


class EntitlementPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_rolling_five_hour_window_does_not_invent_fixed_bounds(self):
        window=rule().window('user:test','test-policy',datetime(2026,11,19,tzinfo=timezone.utc))
        self.assertIsNone(window.start)
        self.assertIsNone(window.end)
        self.assertEqual(window.duration_seconds,18000)
        self.assertIsNotNone(window.ledger_ref)

    def test_natural_day_uses_explicit_timezone(self):
        window=rule(window_type='natural',timezone='Asia/Shanghai',duration_seconds=None).window(
            'user:test','test-policy',datetime(2026,11,19,18,tzinfo=timezone.utc))
        self.assertEqual(window.start.astimezone(timezone.utc),datetime(2026,11,19,16,tzinfo=timezone.utc))
        self.assertEqual((window.end-window.start).total_seconds(),86400)

    def test_fixed_window_at_boundary_enters_new_window(self):
        definition=rule(window_type='fixed',anchor=datetime(2026,1,1,tzinfo=timezone.utc))
        a=definition.window('user:test','policy',datetime(2026,1,1,4,59,tzinfo=timezone.utc))
        b=definition.window('user:test','policy',datetime(2026,1,1,5,tzinfo=timezone.utc))
        self.assertNotEqual(a.window_id,b.window_id)
        self.assertEqual(a.end,b.start)

    async def test_test_policy_is_never_a_production_default(self):
        service=Entitlements(issuer='test',audience='test')
        owner=OwnerEntitlementRow(owner_id='user:test',policy_revision='test',plan_id='test',enabled=True)
        for approved,test_only in ((False,False),(True,True)):
            db=AsyncMock()
            db.get.return_value=EntitlementPolicyRow(policy_revision='test',approved=approved,test_only=test_only,payload={})
            with self.assertRaises(EntitlementError):
                await service.policy(db,owner)

    def test_signing_without_key_fails_closed(self):
        from agent_contracts.v2 import BudgetGrant
        with self.assertRaises(EntitlementError):
            Entitlements(issuer='test',audience='test').sign({},BudgetGrant)
