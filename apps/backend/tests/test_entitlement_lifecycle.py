"""Lifecycle integration tests use only random schemas in a local test database."""
import asyncio
from datetime import datetime, timedelta, timezone
import unittest
from sqlalchemy import select, func
from app.models.agent_entitlements import OwnerEntitlementRow, EntitlementAuditRow, GrantRootRow, EntitlementPolicyRow
from app.services.agent_entitlements.defaults import initialize_free
from app.services.agent_entitlements.dates import add_calendar_months
from app.services.agent_entitlements.lifecycle import reconcile_owner
from app.services.agent_entitlements.assignment import assign_policy
from app.services.agent_entitlements.service import EntitlementError, now_utc
from tests import test_billing_postgres as billing_tests


class CalendarTests(unittest.TestCase):
    def test_shanghai_month_end(self):
        value = datetime(2024, 1, 30, 17, 15, tzinfo=timezone.utc)
        self.assertEqual(add_calendar_months(value, 1).isoformat(), '2024-02-29T01:15:00+08:00')
        self.assertEqual(add_calendar_months(value, 12).isoformat(), '2025-01-31T01:15:00+08:00')
        self.assertEqual(add_calendar_months(datetime(2025, 1, 31, tzinfo=timezone.utc), 1).day, 28)
        with self.assertRaises(ValueError):
            add_calendar_months(datetime(2026, 1, 1), 1)


# Reuse the existing real-Postgres fixture without inheriting unrelated test cases.
@unittest.skipUnless(billing_tests.URL, 'BILLING_TEST_DATABASE_URL not selected')
class LifecyclePostgresTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = billing_tests.BillingPostgresTests.asyncSetUp
    asyncTearDown = billing_tests.BillingPostgresTests.asyncTearDown
    scope = billing_tests.BillingPostgresTests.scope
    migrate = staticmethod(billing_tests.BillingPostgresTests.migrate)
    publish = billing_tests.BillingPostgresTests.publish
    grant = billing_tests.BillingPostgresTests.grant
    request = billing_tests.BillingPostgresTests.request

    async def paid(self, *, enabled=True, expires=True):
        async with self.scope() as db:
            owner, _ = await assign_policy(db, None, 'user:test', 'pro', 'pro-v1-test',
                expires_at=now_utc() - timedelta(days=1) if expires else None)
            owner.enabled = enabled

    async def test_concurrent_registration_preserves_disabled(self):
        async def initialize():
            async with self.scope() as db:
                return await initialize_free(db, 'test')
        self.assertEqual(sorted(await asyncio.gather(initialize(), initialize())), [0, 1])
        async with self.scope() as db:
            (await db.get(OwnerEntitlementRow, 'user:test')).enabled = False
        self.assertEqual(await initialize(), 0)
        async with self.scope() as db:
            self.assertFalse((await db.get(OwnerEntitlementRow, 'user:test')).enabled)
            count = await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(
                EntitlementAuditRow.principal == 'system:registration'))
            self.assertEqual(count, 1)

    async def test_test_policy_does_not_initialize(self):
        async with self.scope() as db:
            (await db.get(EntitlementPolicyRow, 'basic-v1-test')).test_only = True
        async with self.scope() as db:
            self.assertEqual(await initialize_free(db, 'test'), 0)
            self.assertIsNone(await db.get(OwnerEntitlementRow, 'user:test'))

    async def test_expiry_and_audit_are_idempotent(self):
        await self.paid()
        async with self.scope() as db:
            owner, reason = await reconcile_owner(db, 'user:test')
            self.assertIsNone(reason)
            self.assertEqual(owner.plan_id, 'basic')
            self.assertIsNone(owner.expires_at)
        async with self.scope() as db:
            await reconcile_owner(db, 'user:test')
            count = await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(
                EntitlementAuditRow.principal == 'system:expiry'))
            self.assertEqual(count, 1)

    async def test_open_grant_blocks_then_closed_grant_allows_retry(self):
        await self.paid(expires=False)
        async with self.scope() as db:
            _, grant = await self.entitlements.authorize_submission(db, owner_id='user:test', client_key='lifecycle',
                request={'owner_id': 'user:test', 'skills': []})
            (await db.get(OwnerEntitlementRow, 'user:test')).expires_at = now_utc() - timedelta(seconds=1)
        async with self.scope() as db:
            owner, reason = await reconcile_owner(db, 'user:test')
            self.assertEqual(reason, 'ACTIVE_GRANTS_REQUIRE_DRAIN')
            self.assertEqual(owner.plan_id, 'pro')
        with self.assertRaises(EntitlementError):
            async with self.scope() as db:
                await self.entitlements.owner(db, 'user:test')
        async with self.scope() as db:
            (await db.get(GrantRootRow, grant.grant_id)).status = 'closed'
        async with self.scope() as db:
            owner, reason = await reconcile_owner(db, 'user:test')
            self.assertIsNone(reason)
            self.assertEqual(owner.plan_id, 'basic')
            self.assertIsNotNone(await db.get(GrantRootRow, grant.grant_id))

    async def test_disabled_and_permanent_paid_preserved(self):
        await self.paid(enabled=False)
        async with self.scope() as db:
            owner, _ = await reconcile_owner(db, 'user:test')
            self.assertEqual(owner.plan_id, 'pro')
            self.assertFalse(owner.enabled)
            with self.assertRaises(EntitlementError) as error:
                await assign_policy(db, owner, 'user:test', 'basic', 'basic-v1-test')
            self.assertEqual(error.exception.reason, 'ENTITLEMENT_DISABLED')
            owner.enabled = True
            owner.expires_at = None
        async with self.scope() as db:
            owner, _ = await reconcile_owner(db, 'user:test')
            self.assertEqual(owner.plan_id, 'pro')

    async def test_concurrent_expiry_preserves_usage_and_single_audit(self):
        from app.models.agent_entitlements import WindowCounterRow
        await self.paid()
        async with self.scope() as db:
            owner = await db.get(OwnerEntitlementRow, 'user:test')
            row = await db.get(EntitlementPolicyRow, owner.policy_revision)
            from app.services.agent_entitlements.policy import EntitlementPolicy
            policy = EntitlementPolicy.model_validate(row.payload)
            window = policy.rules[0].window(owner.owner_id, owner.policy_revision, now_utc())
            db.add(WindowCounterRow(window_id=window.window_id, owner_id=owner.owner_id,
                rule_id=policy.rules[0].rule_id,
                limit_units=policy.rules[0].limit_units, used=123, held=7,
                window_ref=window.model_dump(mode='json')))
        async def reconcile():
            async with self.scope() as db:
                return (await reconcile_owner(db, 'user:test'))[0].plan_id
        self.assertEqual(await asyncio.wait_for(asyncio.gather(*(reconcile() for _ in range(4))), 10), ['basic'] * 4)
        async with self.scope() as db:
            counter = await db.get(WindowCounterRow, window.window_id)
            self.assertEqual((counter.used, counter.held), (123, 7))
            count = await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(
                EntitlementAuditRow.principal == 'system:expiry'))
            self.assertEqual(count, 1)

    async def test_expiry_missing_basic_fails_closed_then_retries(self):
        await self.paid()
        async with self.scope() as db:
            (await db.get(EntitlementPolicyRow, 'basic-v1-test')).approved = False
        async with self.scope() as db:
            owner, reason = await reconcile_owner(db, 'user:test')
            self.assertEqual((owner.plan_id, reason), ('pro', 'BASIC_POLICY_UNAVAILABLE'))
            with self.assertRaises(EntitlementError):
                await self.entitlements.owner(db, 'user:test')
        async with self.scope() as db:
            (await db.get(EntitlementPolicyRow, 'basic-v1-test')).approved = True
        async with self.scope() as db:
            self.assertEqual((await reconcile_owner(db, 'user:test'))[0].plan_id, 'basic')

    async def test_real_close_after_expiry_allows_basic_on_next_read(self):
        from agent_contracts.v2 import TaskCloseManifest
        from app.services.agent_entitlements.usage import UsageSettlement
        await self.paid(expires=False)
        grant, receipt = await self.grant()
        async with self.scope() as db:
            (await db.get(OwnerEntitlementRow, 'user:test')).expires_at = now_utc() - timedelta(seconds=1)
        manifest = TaskCloseManifest(schema_version=1, manifest_id='expiry-close', agent_audience='agent-test',
            owner_id='user:test', submission_id=grant.submission_id, grant_id=grant.grant_id,
            task_id=receipt.bound_task_id, run_ids=[], execution_ids=[], call_ids=[], permit_ids=[],
            call_count=0, last_task_usage_sequence=0, outbox_ack_high_watermark=0,
            missing_sequences=[], unknown_call_ids=[], all_executions_sealed=True,
            no_startable_permits=True, closed_at=now_utc())
        async with self.scope() as db:
            self.assertEqual(await UsageSettlement(self.entitlements).close(db, manifest), 'settled')
        async with self.scope() as db:
            owner, reason = await reconcile_owner(db, 'user:test')
            self.assertEqual((owner.plan_id, reason), ('basic', None))
            self.assertEqual((await db.get(GrantRootRow, grant.grant_id)).status, 'closed')

    async def test_started_usage_settles_after_expiry_without_resetting_ledger(self):
        from agent_contracts.v2 import PermitStart, UsageDelta, CallStartFact, TaskMeteringBinding
        from agent_contracts.canonical import digest
        from app.models.agent_entitlements import WindowCounterRow, UsageLedgerRow, SubmissionRow
        from app.services.agent_entitlements.usage import UsageSettlement
        await self.paid(expires=False)
        grant, receipt = await self.grant()
        async with self.scope() as db:
            result = await self.entitlements.permit(db, self.request(grant, receipt))
            self.assertEqual(result['decision'], 'authorized')
            permit_id = result['permit']['permit_id']
            started = await self.entitlements.start(db, permit_id, PermitStart(schema_version=1,
                start_operation_id='start', execution_id='execution', control_attestation_id='attestation'))
            profile_id = (await db.get(SubmissionRow, grant.submission_id)).profile_id
            await self.entitlements.bind_metering(db, TaskMeteringBinding(schema_version=1,
                operation_id='bind-expiry', metering_profile_id=profile_id, agent_audience='agent-test',
                task_id=receipt.bound_task_id, owner_id='user:test', request_digest=grant.request_digest,
                submission_id_source='backend', submission_id=grant.submission_id))
        start_at = datetime.fromisoformat(started['committed_at'])
        identity = dict(schema_version=1, agent_audience='agent-test', owner_id='user:test',
            metering_profile_id=profile_id, metering_context='authorized',
            submission_id=grant.submission_id, submission_id_source='backend',
            task_id=receipt.bound_task_id, run_id='run', execution_id='execution',
            call_id='call', logical_call_id='call', control_attestation_id='attestation',
            started_at=start_at, capability_id=self.identity.capability_id,
            capability_version=digest(self.identity.model_dump(mode='json')),
            capability_identity_profile='capability_identity_v1', capability_identity=self.identity.model_dump(mode='json'),
            invocation_mode='internal', purpose='main', parent_call_id=None, activation_id=None,
            grant_id=grant.grant_id, grant_revision=1, reservation_id=grant.reservation_id, permit_id=permit_id)
        fact_body = {**identity, 'fact_kind': 'started', 'start_record_id': 'expiry-start', 'recorded_at': start_at}
        fact = CallStartFact.model_construct(**{**fact_body, 'capability_identity': self.identity}, start_record_digest='pending')
        fact = CallStartFact(**fact_body, start_record_digest=fact.computed_digest())
        usage = UsageDelta(**identity, measurement_id='expiry-measurement', observation_revision=1,
            supersedes_measurement_id=None, logical_attempt=1, transport_attempt=1,
            provider_id='test', provider_request_id='request', phase='completed', outcome='succeeded',
            prompt_tokens=4, completion_tokens=3, usage_status='measured', usage_source='provider_usage',
            missing_reason=None, attempted_units=1, successful_units=1, ended_at=now_utc(),
            observed_at=now_utc(), task_usage_sequence=1)
        async with self.scope() as db:
            (await db.get(OwnerEntitlementRow, 'user:test')).expires_at = now_utc() - timedelta(seconds=1)
        async with self.scope() as db:
            ack = await UsageSettlement(self.entitlements).ingest(db, usage, fact)
            self.assertEqual(ack.disposition, 'accepted', ack)
        async with self.scope() as db:
            await UsageSettlement(self.entitlements).ingest(db, usage, fact)
            counter = await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id == 'daily-tokens'))
            self.assertEqual((counter.used, counter.held), (7, 0))
            self.assertGreater(await db.scalar(select(func.count()).select_from(UsageLedgerRow)), 0)
            self.assertEqual((await reconcile_owner(db, 'user:test'))[1], 'ACTIVE_GRANTS_REQUIRE_DRAIN')
