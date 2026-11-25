"""Cross-service integration using TWO isolated SQLite databases and real SQL.

This verifies durable transactions/round trips, NOT PostgreSQL row-lock races
and NOT a real Provider. No production database or runtime keys are used.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from agent_contracts.canonical import digest
from agent_contracts.execution_v2 import CallIntent, ObservationSubmission, WorkerIdentity
from agent_contracts.signing import verify_signed
from agent_contracts.v2 import (
    BudgetGrant, CallPermitRequest, CallStartFact, GrantBindingReceipt, ModelIdentity,
    PermissionSnapshot, CapabilityPermission, TaskMeteringBinding, TaskSubmissionV2, UsageDelta,
)
from agent_contracts.wire import TaskSubmissionWire
from agent_contracts import TaskSubmission
from agent_app.control import repository
from agent_app.control.metering import MeteringControl, GateDenied
from agent_app.control.usage_delivery import deliver_once
from agent_app.infrastructure.models import Base as AgentBase, RunRow, TaskRow
from agent_app.infrastructure.metering_models import (
    CallRow, ExecutionRow, ObservationRow, TaskMeteringRow, UsageOutboxRow,
)
from app.models.base import Base as BackendBase
from app.models.agent_entitlements import (
    CallPermitRow, EntitlementPolicyRow, GrantRevisionRow, GrantRootRow, OwnerEntitlementRow,
    UsageInboxRow, UsageLedgerRow, UsageProjectionRow, WindowCounterRow,
)
from app.services.agent_entitlements.policy import EntitlementPolicy, EntitlementRule
from app.services.agent_entitlements.service import Entitlements, EntitlementError
from app.services.agent_entitlements.usage import UsageSettlement


class ALinePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await self.create_databases()
        self.key = Ed25519PrivateKey.generate()
        self.service = Entitlements(issuer='backend-test', audience='agent-test', kid='test-key',
                                   private_key=self.key, allow_test_policy=True)
        self.control = MeteringControl(issuer='backend-test', audience='agent-test',
            public_keys={'test-key': self.key.public_key()}, outbox_capacity=100)
        self.usage = UsageSettlement(self.service)
        self.identity = ModelIdentity(schema_version=1, kind='model', capability_id='model:test/m1', provider_id='test',
            registry_model_id='test/m1', upstream_model='m1', configuration_release_digest=digest('test-config'), dependency_digests=[])
        permission = CapabilityPermission(schema_version=1, capability_id=self.identity.capability_id,
            capability_version=digest(self.identity.model_dump(mode='json')), invocation_modes=['internal'],
            purposes=['main','summary'], max_attempts=None, dependency_versions={})
        snapshot = PermissionSnapshot(schema_version=1, permission_snapshot_id='test-snapshot', policy_revision='test-policy',
                                      catalog_revision='static-test', capabilities=[permission])
        self.policy = EntitlementPolicy(schema_version=1, policy_revision='test-policy', plan_id='test-plan', permission_snapshot=snapshot,
            rules=[EntitlementRule(schema_version=1, rule_id='test-tokens', metric='tokens', unit='token', capability_id=None,
                purpose='all', limit_units=100, reservation_units=50, call_upper_bound=20, window_type='fixed',
                accounting_basis='trusted_start', duration_seconds=18000, timezone='UTC', anchor=datetime(2026,1,1,tzinfo=timezone.utc))],
            grant_ttl_seconds=3600, permit_ttl_seconds=60, start_ttl_seconds=10, conservative_clock_skew_ms=0,
            token_scope='prompt_plus_completion', missing_usage_strategy='hold_and_reconcile',
            overage_strategy='record_and_block', unused_release_strategy='sealed_complete_only',
            model_risk_profile='test-risk-explicitly-approved', disable_scope='new_submissions', emergency_scope='grant_root')
        async with self.backend() as db, db.begin():
            db.add(EntitlementPolicyRow(policy_revision='test-policy', approved=True, test_only=True, payload=self.policy.model_dump(mode='json')))
            await db.flush()
            for owner in ('user:test', 'user:other'):
                db.add(OwnerEntitlementRow(owner_id=owner, policy_revision='test-policy', plan_id='test-plan', enabled=True))

    async def create_databases(self):
        self.agent_engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.backend_engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.agent = async_sessionmaker(self.agent_engine, expire_on_commit=False)
        self.backend = async_sessionmaker(self.backend_engine, expire_on_commit=False)
        async with self.agent_engine.begin() as c:
            await c.run_sync(AgentBase.metadata.create_all)
        async with self.backend_engine.begin() as c:
            from app.models import agent_entitlements as model_module
            tables=[v.__table__ for v in vars(model_module).values() if isinstance(v,type) and hasattr(v,'__tablename__')]
            await c.run_sync(lambda conn: BackendBase.metadata.create_all(conn,tables=tables))
    async def asyncTearDown(self):
        await self.agent_engine.dispose()
        await self.backend_engine.dispose()

    async def submit(self, *, key='key', owner='user:test', prompt='research'):
        request = TaskSubmissionWire(owner_id=owner, prompt=prompt, model='test/m1', idempotency_key=key)
        async with self.backend() as db, db.begin():
            submission, grant = await self.service.authorize_submission(db, owner_id=owner, client_key=key,
                                                                       request=request.model_dump(mode='json'))
            self.submission_id, self.grant = submission.submission_id, grant
            self.profile_id = submission.profile_id
        envelope = TaskSubmissionV2(schema_version=1, metering_profile_id=self.profile_id, metering_context='authorized',
            agent_audience='agent-test', owner_id=owner, request_digest=grant.request_digest, submission_id=self.submission_id,
            budget_grant=grant, permission_snapshot=self.policy.permission_snapshot, call_bounds={r.rule_id:r.call_upper_bound for r in self.policy.rules}, request=request)
        async with self.agent() as db:
            task = await repository.submit(db, TaskSubmission(owner_id=owner, prompt=prompt, model='test/m1',
                        idempotency_key='v2:'+self.profile_id), metering=envelope)
            self.task_id = task.task_id
        return task

    async def bind(self):
        async with self.backend() as db, db.begin():
            binding = await self.service.bind_metering(db, TaskMeteringBinding(schema_version=1, operation_id='bind', metering_profile_id=self.profile_id,
                agent_audience='agent-test', task_id=self.task_id, owner_id=self.grant.owner_id,
                request_digest=self.grant.request_digest, submission_id_source='backend', submission_id=self.submission_id))
            self.receipt = await self.service.bind_grant(db, grant_id=self.grant.grant_id, task_id=self.task_id,
                owner_id=self.grant.owner_id, submission_id=self.submission_id, request_digest=self.grant.request_digest,
                expected_revision=1, expected_binding_revision=0)
        async with self.agent() as db, db.begin():
            profile = await db.get(TaskMeteringRow, self.task_id)
            profile.binding, profile.receipt, profile.binding_status = binding.model_dump(mode='json'), self.receipt.model_dump(mode='json'), 'bound'

    async def claim(self, worker='worker'):
        async with self.agent() as db:
            result = await repository.claim_run(db, worker, v2=True)
            self.run, token, _ = result
            execution = await db.scalar(select(ExecutionRow).where(ExecutionRow.run_id == self.run.run_id,
                                                                  ExecutionRow.lease_token == token))
            self.worker = WorkerIdentity(schema_version=1, worker_id=worker, lease_token=token, execution_id=execution.execution_id)

    async def start_call(self, call='call', *, commit_local=True):
        body = CallIntent(**self.worker.model_dump(), call_id=call, logical_call_id='logical', capability_identity=self.identity,
            invocation_mode='internal', purpose='main', parent_call_id=None, activation_id=None, logical_attempt=1,
            transport_attempt=1, provider_id='test', request_digest=digest(['request',call]), input_bound_evidence_ref=None,
            output_bound_evidence_ref=None, risk_profile='test-risk-explicitly-approved',
            model_budget=getattr(self,'model_budget',None))
        async with self.agent() as db, db.begin():
            await self.control.intent(db, self.run.run_id, body)
        async with self.agent() as db:
            request = await self.control.permit_request(db, call)
        async with self.backend() as db, db.begin():
            response = await self.service.permit(db, request)
            self.assertEqual(response['decision'],'authorized',response)
        async with self.agent() as db, db.begin():
            await self.control.attach_permit(db, call, response)
            _, operation = await self.control.prepare_start(db, call, self.worker)
        async with self.backend() as db, db.begin():
            backend_start = await self.service.start(db, response['permit']['permit_id'], operation)
        self.call, self.permit_request_value, self.response, self.operation = call, request, response, operation
        if not commit_local:
            return backend_start
        async with self.agent() as db, db.begin():
            started = await self.control.commit_start(db, call, self.worker, backend_start)
            self.assertTrue(started['may_send'])
        self.call, self.permit_request_value, self.response, self.operation = call, request, response, operation
        return started

    async def finish_call(self, *, key='completion', tokens=7, status='measured', call=None):
        body = ObservationSubmission(**self.worker.model_dump(), observation_submission_id=key, call_id=call or self.call,
            outcome='succeeded', prompt_tokens=tokens if status != 'unknown' else None,
            completion_tokens=3 if status == 'measured' else None, usage_status=status,
            usage_source='provider_usage' if status != 'unknown' else None,
            missing_reason='no_usage' if status == 'unknown' else None, attempted_units=1, successful_units=1,
            provider_request_id='request-id', ended_at=datetime.now(timezone.utc))
        async with self.agent() as db, db.begin():
            usage = await self.control.observe(db, body)
        return usage, body

    async def ingest(self, usage):
        async with self.agent() as db:
            row = await db.get(CallRow, usage.call_id)
            fact = CallStartFact.model_validate(row.start_fact)
        async with self.backend() as db, db.begin():
            return await self.usage.ingest(db, usage, fact)

    async def prepare(self):
        await self.submit()
        await self.bind()
        await self.claim()

    async def flush_usage(self):
        suite = self
        from agent_contracts.v2 import UsageBatch, UsageBatchAck
        class Bridge:
            async def request(self, method, path, payload):
                batch = UsageBatch.model_validate(payload)
                results = [await suite.ingest(item) for item in batch.items]
                return UsageBatchAck(schema_version=1, batch_id=batch.batch_id, results=results).model_dump(mode='json')
        await deliver_once(self.agent, Bridge(), producer_id='agent-test', batch_size=200,
                           max_attempts=5, retry_base_seconds=1, retry_max_seconds=10)

    async def test_v1_and_v2_workers_only_claim_their_protocol_tasks(self):
        from agent_contracts import TaskSubmission
        async with self.agent() as db:
            legacy = await repository.submit(db, TaskSubmission(
                owner_id='legacy-owner', prompt='legacy task', model='test/m1'))
        await self.submit()
        async with self.agent() as db:
            self.assertIsNone(await repository.claim_run(db, 'v2-pending', v2=True))
            legacy_claim = await repository.claim_run(db, 'v1-worker')
            self.assertEqual(legacy_claim[0].task_id, legacy.task_id)
            self.assertIsNone(await repository.claim_run(db, 'v1-second'))
        await self.bind()
        async with self.agent() as db:
            v2_claim = await repository.claim_run(db, 'v2-worker', v2=True)
            self.assertEqual(v2_claim[0].task_id, self.task_id)
            self.assertIsNone(await repository.claim_run(db, 'v1-after-v2-bind'))

    async def test_submission_retries_share_original_reservation_and_conflict(self):
        await self.submit()
        original = self.grant
        await self.submit()
        self.assertEqual(self.grant, original)
        async with self.backend() as db:
            counter = await db.scalar(select(WindowCounterRow))
            self.assertEqual(counter.held,50)
        with self.assertRaises(EntitlementError):
            await self.submit(prompt='different')

    async def test_owner_isolation_and_multitask_competition(self):
        await self.submit(key='one')
        await self.submit(key='two')
        with self.assertRaises(EntitlementError):
            await self.submit(key='three')
        await self.submit(owner='user:other',key='three')

    async def test_receipt_preserves_null_revision_and_cannot_rebind(self):
        await self.submit()
        original = self.grant.model_dump_json()
        await self.bind()
        self.assertEqual(self.grant.model_dump_json(),original)
        self.assertIsNone(self.grant.task_id)
        self.control.verify_receipt(self.grant,self.receipt,self.task_id)
        with self.assertRaises(EntitlementError):
            async with self.backend() as db, db.begin():
                await self.service.bind_grant(db,grant_id=self.grant.grant_id,task_id='other',owner_id='user:test',
                    submission_id=self.submission_id,request_digest=self.grant.request_digest,expected_revision=1,expected_binding_revision=0)

    async def test_start_is_single_use_and_observation_resubmission_no_revision(self):
        await self.prepare()
        await self.start_call()
        async with self.agent() as db, db.begin():
            replay = await self.control.commit_start(db,self.call,self.worker)
            self.assertFalse(replay['may_send'])
        usage, body = await self.finish_call()
        async with self.agent() as db, db.begin():
            replay = await self.control.observe(db,body)
            self.assertEqual(replay.measurement_id,usage.measurement_id)
            self.assertEqual(replay.observation_revision,2)

    async def test_completion_first_and_duplicate_only_charge_once(self):
        await self.prepare()
        await self.start_call()
        completed,_ = await self.finish_call()
        ack = await self.ingest(completed)
        self.assertEqual(ack.missing_revisions,[1])
        async with self.agent() as db:
            started = UsageDelta.model_validate((await db.scalar(select(ObservationRow).where(ObservationRow.revision==1))).payload)
        await self.ingest(started)
        ack = await self.ingest(completed)
        self.assertEqual(ack.disposition,'duplicate')
        async with self.backend() as db:
            counter = await db.scalar(select(WindowCounterRow))
            self.assertEqual((counter.used,counter.held),(10,30))

    async def test_unknown_is_not_zero_and_revision_adjusts_difference_once(self):
        await self.prepare()
        await self.start_call()
        unknown,_ = await self.finish_call(status='unknown')
        await self.ingest(unknown)
        async with self.backend() as db:
            c=await db.scalar(select(WindowCounterRow))
            self.assertEqual((c.used,c.held),(0,50))
        measured,_ = await self.finish_call(key='measured',tokens=7)
        await self.ingest(measured)
        corrected,_=await self.finish_call(key='correction',tokens=9)
        await self.ingest(corrected)
        await self.ingest(corrected)
        async with self.backend() as db:
            c=await db.scalar(select(WindowCounterRow))
            self.assertEqual(c.used,12)
            entries=(await db.scalars(select(UsageLedgerRow).where(UsageLedgerRow.kind=='adjustment'))).all()
            self.assertEqual(sum(e.used_delta for e in entries),2)

    async def test_lease_takeover_blocks_new_start_but_accepts_historical_completion(self):
        await self.prepare()
        await self.start_call()
        old_worker=self.worker
        async with self.agent() as db, db.begin():
            run=await db.get(RunRow,self.run.run_id)
            run.lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        await self.claim('replacement')
        new_worker=self.worker
        self.worker=old_worker
        with self.assertRaises(GateDenied):
            async with self.agent() as db, db.begin():
                await self.control.prepare_start(db,self.call,old_worker)
        completed,_=await self.finish_call()
        await self.ingest(completed)
        self.worker=new_worker
        await self.flush_usage()
        await self.start_call('new-call')
        self.assertNotEqual(self.worker.execution_id,old_worker.execution_id)

    async def test_revocation_prevents_start_and_does_not_refund(self):
        await self.prepare()
        await self.start_call()
        async with self.backend() as db, db.begin():
            await self.service.revoke(db,self.grant.grant_id,'revoke','test-admin','test')
        # Earlier start replays cannot obtain a new send right.
        async with self.backend() as db, db.begin():
            replay=await self.service.start(db,self.response['permit']['permit_id'],self.operation)
            self.assertFalse(replay['first_commit'])
        changed=self.permit_request_value.model_copy(update={'call_id':'later','logical_call_id':'later'})
        async with self.backend() as db, db.begin():
            denied=await self.service.permit(db,changed)
            self.assertEqual(denied['decision'],'denied')
            c=await db.scalar(select(WindowCounterRow))
            self.assertEqual(c.held,50)

    async def test_start_fact_failure_quarantines_then_reprocesses_same_id(self):
        await self.prepare()
        await self.start_call()
        usage,_=await self.finish_call()
        async with self.backend() as db, db.begin():
            ack=await self.usage.ingest(db,usage,None)
            self.assertTrue(ack.durable)
            self.assertEqual(ack.disposition,'quarantined')
            self.assertIsNone(await db.get(UsageProjectionRow,usage.call_id))
        ack=await self.ingest(usage)
        self.assertEqual(ack.disposition,'accepted')

    async def test_overage_preserves_full_measurement_and_blocks_next_call(self):
        await self.prepare()
        await self.start_call()
        usage,_=await self.finish_call(tokens=30)
        await self.ingest(usage)
        async with self.backend() as db, db.begin():
            c=await db.scalar(select(WindowCounterRow))
            root=await db.get(GrantRootRow,self.grant.grant_id)
            self.assertEqual(c.used,33)
            self.assertTrue(root.overage)
            request=self.permit_request_value.model_copy(update={'call_id':'later'})
            self.assertEqual((await self.service.permit(db,request))['decision'],'denied')

    async def reconciliation_fixture(self):
        await self.prepare()
        await self.start_call()
        await self.finish_call(tokens=30)
        await self.flush_usage()
        async with self.agent() as db, db.begin():
            (await db.get(TaskRow, self.task_id)).status = 'completed'
            (await db.get(ExecutionRow, self.worker.execution_id)).sealed = True
            manifest = await self.control.close_manifest(db, self.task_id)
        async with self.backend() as db, db.begin():
            self.assertEqual(await self.usage.close(db, manifest), 'reconciliation_required')
        return {'task_status': 'completed', 'manifest': manifest.model_dump(mode='json')}

    async def test_admin_reconcile_overage_preview_close_and_replay(self):
        from app.services.agent_entitlements.reconciliation import apply
        from app.schemas.admin_plans import ReconcileGrant
        from app.models.agent_entitlements import EntitlementAuditRow
        facts = await self.reconciliation_fixture()
        preview = ReconcileGrant(operation_id='reconcile-preview', reason='reviewed', evidence_ref='test-evidence')
        async with self.backend() as db, db.begin():
            result = await apply(db, self.service, self.grant.grant_id, preview, 'local-admin:test', facts)
            self.assertTrue(result['eligible'])
            self.assertEqual(sum(result['released'].values()), 30)
            self.assertEqual((await db.scalar(select(WindowCounterRow))).held, 30)
        body = preview.model_copy(update={'preview': False, 'operation_id': 'reconcile-execute'})
        async with self.backend() as db, db.begin():
            before = (await db.scalars(select(UsageLedgerRow))).all()
            history = [(e.entry_id, e.held_delta, e.used_delta, e.evidence) for e in before]
            result = await apply(db, self.service, self.grant.grant_id, body, 'local-admin:test', facts)
            self.assertTrue(result['eligible'])
            root = await db.get(GrantRootRow, self.grant.grant_id)
            self.assertEqual(root.status, 'closed')
            self.assertTrue(root.overage)
            counter = await db.scalar(select(WindowCounterRow))
            self.assertEqual((counter.used, counter.held), (33, 0))
        async with self.backend() as db, db.begin():
            self.assertEqual(await apply(db, self.service, self.grant.grant_id, body, 'local-admin:test', {}), result)
            after = (await db.scalars(select(UsageLedgerRow))).all()
            self.assertEqual(len(after), len(history) + 1)
            for entry_id, held, used, evidence in history:
                entry = await db.get(UsageLedgerRow, entry_id)
                self.assertEqual((entry.held_delta, entry.used_delta, entry.evidence), (held, used, evidence))
            self.assertEqual(await db.scalar(select(func.count()).select_from(EntitlementAuditRow).where(
                EntitlementAuditRow.operation_id == body.operation_id)), 1)
            with self.assertRaises(EntitlementError):
                await apply(db, self.service, self.grant.grant_id, body.model_copy(update={'reason':'changed'}), 'local-admin:test', facts)

    async def test_admin_reconcile_rejects_unsafe_conditions_and_audits(self):
        from app.services.agent_entitlements.reconciliation import apply
        from app.schemas.admin_plans import ReconcileGrant
        from app.models.agent_entitlements import EntitlementAuditRow
        facts = await self.reconciliation_fixture()
        body = ReconcileGrant(operation_id='reject-not-complete', reason='reviewed', evidence_ref='test', preview=False)
        for suffix, patch_manifest, reason in [
            ('stale', {'closed_at':(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()}, 'CLOSE_FACTS_STALE'),
            ('manifest', {'last_task_usage_sequence':99}, 'FINAL_CLOSE_MANIFEST_NOT_SUBMITTED'),
        ]:
            async with self.backend() as db, db.begin():
                result = await apply(db, self.service, self.grant.grant_id,
                    body.model_copy(update={'operation_id':'reject-'+suffix}), 'local-admin:test',
                    {**facts, 'manifest':{**facts['manifest'], **patch_manifest}})
                self.assertEqual(result['reason'], reason)
        async with self.backend() as db, db.begin():
            result = await apply(db, self.service, self.grant.grant_id, body, 'local-admin:test',
                                 {**facts, 'task_status':'running'})
            self.assertEqual(result['reason'], 'TASK_NOT_COMPLETED')
            self.assertIsNotNone(await db.scalar(select(EntitlementAuditRow).where(EntitlementAuditRow.operation_id == body.operation_id)))
        async with self.backend() as db, db.begin():
            permit = await db.get(CallPermitRow, self.response['permit']['permit_id'])
            permit.state = 'unknown'
        async with self.backend() as db, db.begin():
            result = await apply(db, self.service, self.grant.grant_id, body.model_copy(update={'operation_id':'reject-unknown-call'}), 'local-admin:test', facts)
            self.assertEqual(result['reason'], 'CLOSE_INCOMPLETE_OR_CALLS_UNSETTLED')
        async with self.backend() as db, db.begin():
            (await db.get(CallPermitRow, self.response['permit']['permit_id'])).state = 'completed'
            (await db.scalar(select(WindowCounterRow))).held += 1
        async with self.backend() as db, db.begin():
            result = await apply(db, self.service, self.grant.grant_id, body.model_copy(update={'operation_id':'reject-ledger-conflict'}), 'local-admin:test', facts)
            self.assertEqual(result['reason'], 'WINDOW_HELD_LEDGER_CONFLICT')
            self.assertEqual((await db.get(GrantRootRow, self.grant.grant_id)).status, 'active')

    async def historical_carry_fixture(self):
        from app.models.agent_entitlements import EntitlementAuditRow
        rule = self.policy.rules[0].model_copy(update={
            'rule_id':'daily-tokens', 'window_type':'natural', 'timezone':'Asia/Shanghai',
            'duration_seconds':None, 'anchor':None})
        self.policy = self.policy.model_copy(update={'rules':[rule]})
        async with self.backend() as db, db.begin():
            (await db.get(EntitlementPolicyRow, self.policy.policy_revision)).payload = self.policy.model_dump(mode='json')
        await self.prepare()
        await self.start_call('carry-source-call')
        await self.finish_call(tokens=7)
        await self.flush_usage()
        source_grant = self.grant.grant_id
        async with self.agent() as db, db.begin():
            (await db.get(TaskRow, self.task_id)).status = 'completed'
            (await db.get(ExecutionRow, self.worker.execution_id)).sealed = True
            manifest = await self.control.close_manifest(db, self.task_id)
        async with self.backend() as db, db.begin():
            self.assertEqual(await self.usage.close(db, manifest), 'settled')
            source = await db.scalar(select(WindowCounterRow))
            source_id = source.window_id
        self.policy = self.policy.model_copy(update={
            'policy_revision':'carry-target-policy',
            'permission_snapshot':self.policy.permission_snapshot.model_copy(update={'policy_revision':'carry-target-policy'})})
        async with self.backend() as db, db.begin():
            db.add(EntitlementPolicyRow(policy_revision=self.policy.policy_revision, approved=True,
                test_only=True, payload=self.policy.model_dump(mode='json')))
            await db.flush()
            (await db.get(OwnerEntitlementRow, 'user:test')).policy_revision = self.policy.policy_revision
        await self.submit(key='carry-target-task')
        await self.bind()
        await self.claim()
        await self.start_call('carry-target-call')
        await self.finish_call(tokens=30)
        await self.flush_usage()
        async with self.agent() as db, db.begin():
            (await db.get(TaskRow, self.task_id)).status = 'completed'
            (await db.get(ExecutionRow, self.worker.execution_id)).sealed = True
            manifest = await self.control.close_manifest(db, self.task_id)
        async with self.backend() as db, db.begin():
            self.assertEqual(await self.usage.close(db, manifest), 'reconciliation_required')
            target = await db.scalar(select(WindowCounterRow).where(WindowCounterRow.window_id != source_id))
            target.used += 10  # Reproduce legacy audited carry without moving historical Usage.
            target_id = target.window_id
            db.add(EntitlementAuditRow(audit_id='historical-carry-audit', operation_id='historical-assignment',
                principal='reviewed-operator', reason='assign', created_at=datetime.now(timezone.utc), payload={
                    'owner_id':'user:test', 'source_policy_revision':'test-policy',
                    'policy_revision':self.policy.policy_revision, 'history_preserved':True,
                    'carried_window_usage':[{'rule_id':'daily-tokens', 'source_window_id':source_id,
                                            'target_window_id':target_id, 'used':10, 'held':0}]}))
        return {'task_status':'completed', 'manifest':manifest.model_dump(mode='json')}, source_id, target_id, source_grant

    async def test_admin_reconcile_accepts_proven_carry_without_changing_usage(self):
        from app.services.agent_entitlements.reconciliation import apply
        from app.schemas.admin_plans import ReconcileGrant
        facts, source_id, target_id, _ = await self.historical_carry_fixture()
        body = ReconcileGrant(operation_id='carry-preview', reason='reviewed', evidence_ref='test')
        async with self.backend() as db, db.begin():
            before = await db.scalar(select(func.count()).select_from(UsageLedgerRow))
            result = await apply(db, self.service, self.grant.grant_id, body, 'local-admin:test', facts)
            self.assertTrue(result['eligible'])
            self.assertEqual(result['historical_carries'][target_id]['used'], 10)
            self.assertEqual((await db.get(WindowCounterRow, target_id)).held, 30)
            self.assertEqual(await db.scalar(select(func.count()).select_from(UsageLedgerRow)), before)
        # Execution exercised only in this isolated fixture, never against real Grants.
        async with self.backend() as db, db.begin():
            result = await apply(db, self.service, self.grant.grant_id,
                body.model_copy(update={'operation_id':'carry-execute', 'preview':False}), 'local-admin:test', facts)
            self.assertTrue(result['eligible'])
            self.assertEqual((await db.get(WindowCounterRow, source_id)).used, 10)
            target = await db.get(WindowCounterRow, target_id)
            self.assertEqual((target.used, target.held), (43, 0))
            entry = await db.scalar(select(UsageLedgerRow).where(UsageLedgerRow.operation_key.startswith('reconcile-close:')))
            self.assertEqual(entry.evidence['historical_carry']['audit_id'], 'historical-carry-audit')
            self.assertEqual(entry.used_delta, 0)
            self.assertTrue((await db.get(GrantRootRow, self.grant.grant_id)).overage)

    async def test_admin_reconcile_rejects_unproven_or_ambiguous_carries(self):
        from copy import deepcopy
        from app.models.agent_entitlements import EntitlementAuditRow
        from app.services.agent_entitlements.reconciliation import apply
        from app.schemas.admin_plans import ReconcileGrant
        facts, source_id, target_id, source_grant = await self.historical_carry_fixture()
        cases = [('missing','CARRY_AUDIT_MISSING_OR_AMBIGUOUS'),
                 ('duplicate','CARRY_AUDIT_MISSING_OR_AMBIGUOUS'),
                 ('amount','CARRY_AMOUNT_CONFLICT'), ('owner','CARRY_IDENTITY_CONFLICT'),
                 ('day','CARRY_WINDOW_CONFLICT'), ('source-ledger','CARRY_SOURCE_LEDGER_CONFLICT'),
                 ('late-source-entry','CARRY_SOURCE_CHANGED_OR_UNVERIFIED'),
                 ('source-active','CARRY_SOURCE_GRANT_UNSETTLED'),
                 ('source-unknown','CARRY_SOURCE_CLOSE_INCOMPLETE')]
        for case, reason in cases:
            with self.subTest(case=case):
                async with self.backend() as db:
                    audit = await db.get(EntitlementAuditRow, 'historical-carry-audit')
                    source = await db.get(WindowCounterRow, source_id)
                    if case == 'missing':
                        await db.delete(audit)
                    elif case == 'duplicate':
                        db.add(EntitlementAuditRow(audit_id='duplicate-carry', operation_id='duplicate-carry',
                            principal=audit.principal, reason=audit.reason, created_at=audit.created_at, payload=deepcopy(audit.payload)))
                    elif case == 'amount':
                        payload = deepcopy(audit.payload); payload['carried_window_usage'][0]['used'] = 11
                        audit.payload = payload
                    elif case == 'owner':
                        source.owner_id = 'user:other'
                    elif case == 'day':
                        source.window_ref = {**source.window_ref, 'end':'2030-01-02T00:00:00Z'}
                    elif case == 'source-ledger':
                        source.used += 1
                    elif case == 'late-source-entry':
                        entry = await db.scalar(select(UsageLedgerRow).where(UsageLedgerRow.grant_id == source_grant))
                        entry.created_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                    elif case == 'source-active':
                        (await db.get(GrantRootRow, source_grant)).status = 'active'
                    elif case == 'source-unknown':
                        projection = await db.scalar(select(UsageProjectionRow).where(UsageProjectionRow.call_id == 'carry-source-call'))
                        projection.settlement_status = 'reconciliation_required'
                    result = await apply(db, self.service, self.grant.grant_id,
                        ReconcileGrant(operation_id='reject-carry-'+case, reason='test', evidence_ref='test'),
                        'local-admin:test', facts)
                    self.assertFalse(result['eligible'])
                    self.assertEqual(result['reason'], reason)
                    self.assertEqual((await db.get(WindowCounterRow, target_id)).held, 30)
                    await db.rollback()

    async def test_pending_settlement_keeps_outbox_without_blocking_new_calls(self):
        from agent_app.control.usage_delivery import settle_observation
        from agent_contracts.v2 import UsageBatch, UsageBatchAck
        await self.prepare()
        await self.start_call()
        completed, _ = await self.finish_call()
        class Unavailable:
            async def request(self, *args):
                raise TimeoutError('offline test')
        async with self.agent() as db:
            with self.assertRaises(TimeoutError):
                await settle_observation(db, Unavailable(), completed)
        # Pending usage remains reserved at Backend; it does not globally
        # block another call while the durable Outbox is below its cap.
        await self.start_call('before-ack')
        async with self.agent() as db:
            self.assertEqual((await db.get(UsageOutboxRow, completed.measurement_id)).state, 'pending')
        suite = self
        class Bridge:
            async def request(self, method, path, payload):
                batch = UsageBatch.model_validate(payload)
                return UsageBatchAck(schema_version=1, batch_id=batch.batch_id,
                    results=[await suite.ingest(item) for item in batch.items]).model_dump(mode='json')
        for _ in range(2):
            async with self.agent() as db:
                await settle_observation(db, Bridge(), completed)
        async with self.backend() as db:
            counter = await db.scalar(select(WindowCounterRow))
            self.assertEqual((counter.used, counter.held), (10, 30))

    async def test_partial_retains_unmeasured_reservation(self):
        await self.prepare()
        await self.start_call()
        usage, _ = await self.finish_call(status='partial')
        await self.ingest(usage)
        async with self.backend() as db:
            counter = await db.scalar(select(WindowCounterRow))
            self.assertEqual((counter.used, counter.held), (7, 43))

    async def test_other_task_permit_and_preissued_start_observe_owner_window_overage(self):
        await self.prepare()
        await self.start_call()
        first_call = self.call
        first_request = self.permit_request_value
        # Two distinct Tasks may reserve the same owner window before settlement.
        await self.submit(key='second-task')
        await self.bind()
        from agent_contracts.v2 import RequestedAllocation, PermitStart
        second_request = first_request.model_copy(update={
            'call_id': 'second-call', 'control_attestation_id': 'second-attestation',
            'grant_id': self.grant.grant_id, 'submission_id': self.grant.submission_id,
            'reservation_id': self.grant.reservation_id, 'task_id': self.task_id,
            'binding_receipt_id': self.receipt.receipt_id,
            'requested_allocations': [RequestedAllocation(schema_version=1, allocation_id=self.grant.allocations[0].allocation_id,
                metric='tokens', unit='token', upper_bound_units=20)]})
        async with self.backend() as db, db.begin():
            response = await self.service.permit(db, second_request)
            self.assertEqual(response['decision'], 'authorized')
        usage, _ = await self.finish_call(tokens=120, call=first_call)
        await self.ingest(usage)
        async with self.backend() as db, db.begin():
            root = await db.get(GrantRootRow, self.grant.grant_id)
            self.assertFalse(root.overage)  # Only the other Task crossed its bound.
            denied = await self.service.permit(db, second_request.model_copy(update={'call_id': 'third-call'}))
            self.assertEqual(denied['reason_code'], 'QUOTA_EXHAUSTED')
        with self.assertRaises(EntitlementError) as error:
            async with self.backend() as db, db.begin():
                await self.service.start(db, response['permit']['permit_id'], PermitStart(schema_version=1,
                    start_operation_id='second-start', execution_id=second_request.execution_id,
                    control_attestation_id='second-attestation'))
        self.assertEqual(error.exception.reason, 'QUOTA_EXHAUSTED')

    async def test_close_missing_usage_never_releases_reservation(self):
        await self.prepare()
        await self.start_call()
        async with self.agent() as db, db.begin():
            task=await db.get(TaskRow,self.task_id)
            task.status='failed'
            run=await db.get(RunRow,self.run.run_id)
            run.lease_expires_at=None
            await self.control.recover_execution(db,self.worker.execution_id)
            manifest=await self.control.close_manifest(db,self.task_id)
        async with self.backend() as db, db.begin():
            self.assertEqual(await self.usage.close(db,manifest),'reconciliation_required')
            c=await db.scalar(select(WindowCounterRow))
            self.assertEqual(c.held,50)

    async def test_outbox_ack_loss_retries_same_measurements(self):
        await self.prepare()
        await self.start_call()
        await self.finish_call()
        parent=self
        class Backend:
            lose=True
            async def request(self,method,path,payload):
                from agent_contracts.v2 import UsageBatch,UsageBatchAck
                batch=UsageBatch.model_validate(payload)
                results=[await parent.ingest(item) for item in batch.items]
                if self.lose:
                    self.lose=False
                    raise TimeoutError('Ack lost AFTER commit')
                return UsageBatchAck(schema_version=1, batch_id=batch.batch_id,results=results).model_dump(mode='json')
        backend=Backend()
        args=dict(producer_id='test',batch_size=20,max_attempts=5,retry_base_seconds=1,retry_max_seconds=10)
        with self.assertRaises(TimeoutError):
            await deliver_once(self.agent,backend,**args)
        async with self.agent() as db, db.begin():
            for row in (await db.scalars(select(UsageOutboxRow))).all():
                row.available_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        self.assertEqual(await deliver_once(self.agent,backend,**args),2)
        async with self.backend() as db:
            c=await db.scalar(select(WindowCounterRow))
            self.assertEqual(c.used,10)
            self.assertEqual(await db.scalar(select(func.count()).select_from(UsageInboxRow)),2)

    async def test_signature_types_wrong_kid_and_noncanonical_claims(self):
        await self.submit()
        await self.bind()
        verify_signed(self.grant,issuer='backend-test',audience='agent-test',public_keys={'test-key':self.key.public_key()})
        for value in (self.grant.model_copy(update={'owner_id':'user:other'}),
                      self.grant.model_copy(update={'signature':self.receipt.signature})):
            with self.assertRaises(ValueError):
                verify_signed(value,issuer='backend-test',audience='agent-test',public_keys={'test-key':self.key.public_key()})
        with self.assertRaises(ValueError):
            verify_signed(self.grant,issuer='backend-test',audience='agent-test',public_keys={})

    async def test_revision_cas_keeps_historical_null_payload(self):
        await self.submit()
        await self.bind()
        async with self.backend() as db, db.begin():
            revision=await self.service.revise(db,self.grant.grant_id,expected_revision=1,expected_binding_revision=1,
                                               expires_at=self.grant.expires_at+timedelta(minutes=1))
            self.assertEqual((revision.task_id,revision.binding_receipt_id),(self.task_id,self.receipt.receipt_id))
            old=await db.get(GrantRevisionRow,(self.grant.grant_id,1))
            self.assertIsNone(old.payload['task_id'])
            self.assertEqual(self.receipt.grant_payload_digest,old.payload_digest)
        with self.assertRaises(EntitlementError):
            async with self.backend() as db, db.begin():
                await self.service.revise(db,self.grant.grant_id,expected_revision=1,expected_binding_revision=1,expires_at=revision.expires_at)

    async def test_http_submit_permit_provider_delivery_close_and_trusted_query(self):
        await self.http_flow()

    async def test_http_dynamic_budget_reaches_provider_and_settles(self):
        await self.http_flow(dynamic=True)

    async def test_http_overage_returns_current_result_and_blocks_next_provider_and_task(self):
        await self.http_flow(overage=True)

    async def http_flow(self, overage=False, dynamic=False):
        """Two ASGI services + separate SQL DBs + actual MockTransport sends."""
        from contextlib import asynccontextmanager
        import os
        import tempfile
        from unittest.mock import patch
        import httpx
        from fastapi import FastAPI
        from app.api import agent_v2 as backend_api
        from app.services.agent_gateway import v2 as gateway_module
        from agent_app.api import v2 as agent_api
        from agent_app.infrastructure.database import get_session
        from agent_app.execution.metering import WorkerMeter,current_meter,model_identity
        from agent_app.integrations.llm.agent_stream import OpenAICompatProvider
        from agent_app.integrations.llm.config import ModelConfig
        from agent_app.execution.provider import ModelRequest
        from agent_app.worker.host import AgentControlClient
        backend_app,agent_app=FastAPI(),FastAPI()
        backend_app.include_router(backend_api.router)
        agent_app.include_router(agent_api.router)
        async def agent_db():
            async with self.agent() as db:
                yield db
        @asynccontextmanager
        async def backend_scope():
            async with self.backend() as db,db.begin():
                yield db
        agent_app.dependency_overrides[get_session]=agent_db
        agent_app.dependency_overrides[agent_api.metering_control]=lambda:self.control
        backend_app.dependency_overrides[backend_api.entitlement_service]=lambda:self.service
        agent_transport=httpx.ASGITransport(app=agent_app)
        backend_transport=httpx.ASGITransport(app=backend_app)
        class Bridge:
            async def request(inner,method,path,payload=None):
                async with httpx.AsyncClient(transport=backend_transport,base_url='http://backend.invalid',
                    headers={'Authorization':'Bearer control-test'}) as client:
                    response=await client.request(method,'/api/v2/agent/internal'+path,json=payload)
                self.assertLess(response.status_code,400,response.text)
                return response.json()
        sends=[]
        def provider_send(request):
            sends.append(request)
            if dynamic:self.assertEqual(json.loads(request.content)['max_tokens'],100)
            return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n'
                + 'data: ' + json.dumps({'choices': [], 'usage': {'prompt_tokens': 120 if overage else 7, 'completion_tokens': 3}}) + '\n\ndata: [DONE]\n\n')
        with tempfile.TemporaryDirectory() as spool,patch.dict(os.environ,{
            'AGENT_GATEWAY_TOKEN':'gateway-test','AGENT_FACT_READER_TOKEN':'reader-test',
            'AGENT_WORKER_TOKEN':'worker-test','AGENT_CONTROL_TOKEN':'control-test','AGENT_SERVICE_TOKEN':'legacy-test',
            'AGENT_V2_ADMISSION':'authorized','AGENT_MODEL_ROUTE_REVISION':'test-route',
            'AGENT_USAGE_SPOOL_ROOT':spool,'BACKEND_BFF_SECRET':'bff-test'}),patch.object(backend_api,'session_scope',backend_scope),\
            patch.object(gateway_module,'session_scope',backend_scope),patch.object(gateway_module,'entitlement_service',lambda:self.service),\
            patch.object(agent_api,'EntitlementClient',Bridge),\
            patch.object(backend_api,'AgentGatewayV2',lambda:gateway_module.AgentGatewayV2(transport=agent_transport)):
            provider=OpenAICompatProvider(ModelConfig(key='test-only',base_url='https://provider.invalid/v1',model='qwen-plus',
                models=('qwen-plus',),provider='dashscope'),transport=httpx.MockTransport(provider_send))
            resolved=provider.registry.resolve_model('qwen-plus','agent')
            identity=model_identity(resolved)
            permission=self.policy.permission_snapshot.capabilities[0].model_copy(update={
                'capability_id':identity.capability_id,'capability_version':digest(identity.model_dump(mode='json'))})
            self.policy=self.policy.model_copy(update={'permission_snapshot':self.policy.permission_snapshot.model_copy(update={'capabilities':[permission]})})
            if dynamic:
                from app.services.agent_entitlements.policy import ModelBudgetProfile
                self.policy=self.policy.model_copy(update={'dynamic_model_budget':True,'reservation_mode':'per_call',
                    'rules':[r.model_copy(update={'limit_units':100000}) for r in self.policy.rules],
                    'model_budget_profiles':{identity.capability_id:ModelBudgetProfile(schema_version=1,
                        input_basis='risk_assessed_utf8_v1',input_overhead_tokens=10,context_window_tokens=4096,
                        max_output_tokens=100,output_limit_semantics='completion_including_reasoning')}})
            async with self.backend() as db,db.begin():
                row=await db.get(EntitlementPolicyRow,'test-policy')
                row.payload=self.policy.model_dump(mode='json')
            async with httpx.AsyncClient(transport=backend_transport,base_url='http://backend.invalid',
                headers={'x-shenzhi-bff-secret':'bff-test','x-shenzhi-user-id':'test','Idempotency-Key':'http-test'}) as browser:
                # Obsolete V1 admission settings cannot affect V2 execution.
                with patch.dict(os.environ, {'AGENT_V1_ADMISSION':'legacy'}):
                    held=await browser.post('/api/v2/agent/submissions',json={'schema_version':1,'prompt':'research','model':resolved.spec.id})
                self.assertEqual(held.status_code,200,held.text)
                response=await browser.post('/api/v2/agent/submissions',json={'schema_version':1,'prompt':'research','model':resolved.spec.id})
                self.assertEqual(response.status_code,200,response.text)
                task=response.json()['task']
                # Product retry reuses the durable Submission and original Task.
                replay=await browser.post('/api/v2/agent/submissions',json={'schema_version':1,'prompt':'research','model':resolved.spec.id})
                self.assertEqual(replay.status_code,200,replay.text)
                self.assertEqual(replay.json()['task']['task_id'],task['task_id'])
                with patch.dict(os.environ,{'AGENT_V2_ADMISSION':'observation_only'}):
                    pinned=await browser.post('/api/v2/agent/submissions',json={'schema_version':1,'prompt':'research','model':resolved.spec.id})
                    self.assertEqual(pinned.status_code,200,pinned.text)
                    self.assertEqual(pinned.json()['task']['metering_context'],'authorized')
                async with self.backend() as db,db.begin():
                    root=await db.scalar(select(GrantRootRow))
                    revision=await self.service.revise(db,root.grant_id,expected_revision=1,expected_binding_revision=1,
                        expires_at=(await db.get(GrantRevisionRow,(root.grant_id,1))).payload['expires_at'])
                replay=await browser.post('/api/v2/agent/submissions',json={'schema_version':1,'prompt':'research','model':resolved.spec.id})
                self.assertEqual(replay.status_code,200,replay.text)
                control_client=AgentControlClient(transport=agent_transport)
                try:
                    claim=await control_client.claim('http-worker')
                    self.assertIsNotNone(claim['run'])
                    control_client.execution_id=claim['execution_id']
                    meter=WorkerMeter(control_client,run_id=claim['run']['run_id'],execution_id=claim['execution_id'],
                        worker_id='http-worker',lease_token=claim['lease_token'],context='authorized',stop=asyncio.Event(),
                        risk_profile='test-risk-explicitly-approved',dynamic_budget=claim.get('dynamic_model_budget',False))
                    token=current_meter.set(meter)
                    try:
                        events=[event async for event in provider.stream(ModelRequest(resolved.spec.id,[]))]
                    finally:
                        current_meter.reset(token)
                    self.assertEqual(len(sends),1)
                    self.assertFalse(list(Path(spool).glob('*.json')))
                    if overage:
                        from agent_app.errors import BusinessError
                        # No asynchronous delivery worker runs between calls.
                        # Completion's synchronous fast path must already block.
                        token=current_meter.set(meter)
                        try:
                            with self.assertRaises(BusinessError):
                                _=[event async for event in provider.stream(ModelRequest(resolved.spec.id,[]))]
                        finally:
                            current_meter.reset(token)
                        self.assertEqual(len(sends),1)
                        browser.headers['Idempotency-Key']='cannot-bypass-by-new-task'
                        denied=await browser.post('/api/v2/agent/submissions',json={'schema_version':1,'prompt':'another','model':resolved.spec.id})
                        self.assertEqual(denied.status_code,403,denied.text)
                        self.assertEqual(denied.json()['error']['reason_code'],'QUOTA_EXHAUSTED')
                        return
                    await deliver_once(self.agent,Bridge(),producer_id='agent-test',batch_size=20,max_attempts=5,
                                       retry_base_seconds=1,retry_max_seconds=10)
                    projected=await browser.get(f"/api/v2/agent/tasks/{task['task_id']}/usage")
                    self.assertEqual(projected.status_code,200,projected.text)
                    self.assertEqual(projected.json()['measured_tokens'],10)
                    await control_client.post(f"/internal/v2/runs/{claim['run']['run_id']}/report",dict(
                        worker_id='http-worker',lease_token=claim['lease_token'],run_id=claim['run']['run_id'],
                        task_id=task['task_id'],status='completed',result={},usage={},error_code=None,error_message=None))
                    async with self.agent() as db:
                        manifest=await self.control.close_manifest(db,task['task_id'])
                    closed=await Bridge().request('POST',f'/grants/{manifest.grant_id}/close',manifest.model_dump(mode='json'))
                    self.assertEqual(closed['settlement_status'],'settled')
                    projected=(await browser.get(f"/api/v2/agent/tasks/{task['task_id']}/usage")).json()
                    self.assertEqual(projected['settlement_status'],'settled')
                    self.assertTrue(all(a['held']==0 for a in projected['allocations'].values()))
                finally:
                    await control_client.close()

    async def test_local_start_refreshes_cached_lease_after_remote_saga(self):
        await self.prepare()
        backend_start=await self.start_call(commit_local=False)
        old_worker=self.worker
        async with self.agent() as stale:
            cached_run=await stale.get(RunRow,self.run.run_id)
            cached_task=await stale.get(TaskRow,self.task_id)
            await stale.commit()
            async with self.agent() as db,db.begin():
                run=await db.get(RunRow,self.run.run_id)
                run.lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            await self.claim('takeover')
            self.assertEqual(cached_run.lease_token,old_worker.lease_token)
            with self.assertRaises(GateDenied):
                await self.control.commit_start(stale,self.call,old_worker,backend_start)

    async def test_sealed_unstarted_intent_can_void_but_does_not_refund_until_close(self):
        from agent_contracts.v2 import VoidProof
        await self.prepare()
        backend_start=await self.start_call(commit_local=False)
        async with self.agent() as db,db.begin():
            task=await db.get(TaskRow,self.task_id)
            task.status='failed'
            run=await db.get(RunRow,self.run.run_id)
            run.lease_expires_at=None
            await self.control.recover_execution(db,self.worker.execution_id)
            seal=await self.control.seal_unstarted(db,self.call)
        proof=VoidProof(**dict(seal,schema_version=1,backend_start_authorization_id=backend_start['start_authorization_id']))
        async with self.backend() as db,db.begin():
            await self.service.void(db,proof)
            self.assertEqual((await db.scalar(select(WindowCounterRow))).held,50)
        async with self.agent() as db,db.begin():
            row=await db.get(CallRow,self.call)
            row.remote_closed=True
        async with self.agent() as db:
            manifest=await self.control.close_manifest(db,self.task_id)
        async with self.backend() as db,db.begin():
            self.assertEqual(await self.usage.close(db,manifest),'settled')
            self.assertEqual((await db.scalar(select(WindowCounterRow))).held,0)

    async def test_started_receipt_can_never_be_voided(self):
        await self.prepare()
        await self.start_call()
        async with self.agent() as db,db.begin():
            run=await db.get(RunRow,self.run.run_id)
            run.lease_expires_at=None
            await self.control.recover_execution(db,self.worker.execution_id)
            with self.assertRaises(GateDenied):
                await self.control.seal_unstarted(db,self.call)

    async def test_observation_only_is_backend_bound_and_never_creates_authorization(self):
        request=TaskSubmissionWire(owner_id='user:test',prompt='observe',model='test/m1',idempotency_key='obs-test')
        async with self.backend() as db,db.begin():
            profile=await self.service.prepare_profile(db,owner_id='user:test',request_digest=digest(request.model_dump(mode='json')),
                                                        admission_revision='test-a1')
            self.profile_id=profile.profile_id
        envelope=TaskSubmissionV2(schema_version=1, metering_profile_id=self.profile_id,metering_context='observation_only',
            agent_audience='agent-test',owner_id='user:test',request_digest=digest(request.model_dump(mode='json')),
            submission_id=None,budget_grant=None,permission_snapshot=None,call_bounds={},request=request)
        async with self.agent() as db:
            task=await repository.submit(db,TaskSubmission(owner_id='user:test',prompt='observe',model='test/m1'),metering=envelope)
            self.task_id=task.task_id
            local=await db.get(TaskMeteringRow,self.task_id)
            observation_id=local.submission_id
        self.assertTrue(observation_id.startswith('obs:'))
        async with self.backend() as db,db.begin():
            binding=await self.service.bind_metering(db,TaskMeteringBinding(schema_version=1, operation_id='obs-bind',metering_profile_id=self.profile_id,
                agent_audience='agent-test',task_id=self.task_id,owner_id='user:test',request_digest=envelope.request_digest,
                submission_id_source='agent_observation',submission_id=observation_id))
        async with self.agent() as db,db.begin():
            local=await db.get(TaskMeteringRow,self.task_id)
            local.binding_status,local.binding='bound',binding.model_dump(mode='json')
        await self.claim()
        body=CallIntent(**self.worker.model_dump(),call_id='observation-call',logical_call_id='logical',capability_identity=self.identity,
            invocation_mode='internal',purpose='summary',parent_call_id=None,activation_id=None,logical_attempt=1,transport_attempt=1,
            provider_id='test',request_digest=digest('observe'),input_bound_evidence_ref=None,output_bound_evidence_ref=None,risk_profile=None)
        async with self.agent() as db,db.begin():
            await self.control.intent(db,self.run.run_id,body)
            await self.control.prepare_start(db,body.call_id,self.worker)
            await self.control.commit_start(db,body.call_id,self.worker)
        self.call=body.call_id
        usage,_=await self.finish_call()
        self.assertIsNone(usage.grant_id)
        receipt=await self.ingest(usage)
        self.assertEqual(receipt.settlement_status,'pending')  # started revision still needs delivery
        async with self.backend() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(GrantRootRow)),0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(UsageLedgerRow)),0)
        from agent_contracts.v2 import SkillIdentity
        skill=SkillIdentity(schema_version=1, kind='skill',capability_id='skill:test',resource_content_digest=digest('resources'),dependency_digests=[])
        activation=body.model_copy(update={'call_id':'skill-call','capability_identity':skill,'purpose':'skill_activation',
                                           'activation_id':'activation-1','invocation_mode':'forced','provider_id':None})
        async with self.agent() as db,db.begin():
            await self.control.intent(db,self.run.run_id,activation)
            await self.control.prepare_start(db,activation.call_id,self.worker)
            await self.control.commit_start(db,activation.call_id,self.worker)
            completed=await self.control.observe(db,ObservationSubmission(**self.worker.model_dump(),
                observation_submission_id='skill-complete',call_id=activation.call_id,outcome='succeeded',
                prompt_tokens=None,completion_tokens=None,usage_status='measured',usage_source='not_applicable',
                missing_reason=None,attempted_units=1,successful_units=1,provider_request_id=None,
                ended_at=datetime.now(timezone.utc)))
            self.assertEqual(completed.phase,'activation')
        async with self.agent() as db,db.begin():
            repeated=await self.control.intent(db,self.run.run_id,activation.model_copy(update={
                'call_id':'skill-repeat','activation_id':'activation-2','invocation_mode':'model_selected'}))
            self.assertEqual(repeated.call_id,activation.call_id)
            self.assertEqual(await db.scalar(select(func.count()).select_from(CallRow).where(CallRow.activation_key.is_not(None))),1)

    async def test_new_run_reuses_task_reservation_instead_of_replenishing_it(self):
        from agent_contracts import ExecutionReport,RunStatus
        await self.prepare()
        await self.start_call()
        usage,_=await self.finish_call()
        await self.ingest(usage)
        async with self.agent() as db:
            await repository.record_report(db,ExecutionReport(run_id=self.run.run_id,task_id=self.task_id,
                status=RunStatus.FAILED,error_code='test-retry'),self.worker.worker_id,self.worker.lease_token)
            from agent_app.infrastructure.models import OutboxRow
            for row in (await db.scalars(select(OutboxRow))).all():
                row.available_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            await db.commit()
        old_run=self.run.run_id
        await self.claim('retry-worker')
        self.assertNotEqual(self.run.run_id,old_run)
        await self.flush_usage()
        await self.start_call('retry-call')
        usage,_=await self.finish_call(key='retry-completion')
        await self.ingest(usage)
        async with self.backend() as db:
            counter=await db.scalar(select(WindowCounterRow))
            self.assertEqual((counter.used,counter.held),(20,10))
            self.assertEqual(await db.scalar(select(func.count()).select_from(GrantRootRow)),1)

    async def test_lost_permit_response_is_closed_by_a_serialized_tombstone(self):
        from agent_contracts.execution_v2 import AbandonCall
        await self.prepare()
        body=CallIntent(**self.worker.model_dump(),call_id='lost-permit',logical_call_id='logical',capability_identity=self.identity,
            invocation_mode='internal',purpose='main',parent_call_id=None,activation_id=None,logical_attempt=1,transport_attempt=1,
            provider_id='test',request_digest=digest('request'),input_bound_evidence_ref=None,output_bound_evidence_ref=None,
            risk_profile='test-risk-explicitly-approved')
        async with self.agent() as db,db.begin():
            await self.control.intent(db,self.run.run_id,body)
            request=await self.control.permit_request(db,body.call_id)
        # Simulate a network request still delayed BEFORE reaching Backend.
        async with self.agent() as db,db.begin():
            task=await db.get(TaskRow,self.task_id)
            task.status='failed'
            run=await db.get(RunRow,self.run.run_id)
            run.lease_expires_at=None
            await self.control.recover_execution(db,self.worker.execution_id)
            seal=await self.control.seal_unstarted(db,body.call_id)
        proof=AbandonCall(schema_version=1, request=request,**{k:seal[k] for k in ('void_operation_id','sealed_intent_revision','sealed_at',
            'start_operation_id','local_started_record_absent','local_start_receipt_never_issued','reason_code')})
        async with self.backend() as db,db.begin():
            abandoned=await self.service.abandon_request(db,proof)
        # Delayed original authorize can no longer create a spendable permit.
        async with self.backend() as db,db.begin():
            delayed=await self.service.permit(db,request)
            self.assertEqual(delayed['decision'],'denied')
            self.assertEqual((await db.scalar(select(WindowCounterRow))).held,50)
        async with self.agent() as db,db.begin():
            row=await db.get(CallRow,body.call_id)
            row.permit,row.remote_closed=abandoned['response'],True
            manifest=await self.control.close_manifest(db,self.task_id)
        async with self.backend() as db,db.begin():
            self.assertEqual(await self.usage.close(db,manifest),'settled')

    async def test_multiple_windows_roll_back_all_reservations_if_one_is_full(self):
        daily=self.policy.rules[0].model_copy(update={'rule_id':'test-daily','window_type':'natural',
            'timezone':'Asia/Shanghai','duration_seconds':None,'anchor':None,'limit_units':50})
        self.policy=self.policy.model_copy(update={'rules':[*self.policy.rules,daily]})
        async with self.backend() as db,db.begin():
            row=await db.get(EntitlementPolicyRow,'test-policy')
            row.payload=self.policy.model_dump(mode='json')
        await self.submit(key='first')
        with self.assertRaises(EntitlementError):
            await self.submit(key='second')
        async with self.backend() as db:
            counters=(await db.scalars(select(WindowCounterRow))).all()
            self.assertEqual(len(counters),2)
            self.assertEqual([c.held for c in counters],[50,50])

    async def test_exact_capability_revocation_and_token_scope_are_explicit_policy(self):
        self.policy=self.policy.model_copy(update={'emergency_scope':'grant_capability','token_scope':'prompt_only'})
        async with self.backend() as db,db.begin():
            row=await db.get(EntitlementPolicyRow,'test-policy')
            row.payload=self.policy.model_dump(mode='json')
        await self.prepare()
        await self.start_call()
        usage,_=await self.finish_call()
        await self.ingest(usage)
        async with self.backend() as db,db.begin():
            self.assertEqual((await db.scalar(select(WindowCounterRow))).used,7)
            await self.service.revoke(db,self.grant.grant_id,'exact-revoke','test-admin','exact-test',
                capability_id=self.identity.capability_id,capability_version=digest(self.identity.model_dump(mode='json')))
            self.assertEqual((await db.get(GrantRootRow,self.grant.grant_id)).status,'active')
            denied=await self.service.permit(db,self.permit_request_value.model_copy(update={'call_id':'after-revoke'}))
            self.assertEqual(denied['reason_code'],'CAPABILITY_REVOKED')

    async def test_conflicting_measurement_is_audited_without_overwriting_raw_usage(self):
        await self.prepare()
        await self.start_call()
        usage,_=await self.finish_call()
        await self.ingest(usage)
        altered=usage.model_copy(update={'prompt_tokens':99})
        ack=await self.ingest(altered)
        self.assertEqual((ack.disposition,ack.durable),('rejected',False))
        async with self.backend() as db:
            raw=await db.get(UsageInboxRow,usage.measurement_id)
            self.assertEqual(raw.payload['prompt_tokens'],7)
            self.assertEqual((await db.scalar(select(WindowCounterRow))).used,10)

    async def test_operator_adjustment_is_idempotent_and_keeps_provider_fact(self):
        from app.services.agent_entitlements.operations import adjust_usage
        await self.prepare()
        await self.start_call()
        usage,_=await self.finish_call()
        await self.ingest(usage)
        fields=dict(operation_id='adjust-test',principal='test-admin',allocation_id=self.grant.allocations[0].allocation_id,
            used_delta=-2,reason='test-credit',evidence_ref='test-evidence',effective_started_at=usage.started_at)
        for _ in range(2):
            async with self.backend() as db,db.begin():
                await adjust_usage(db,self.service,**fields)
        async with self.backend() as db:
            self.assertEqual((await db.scalar(select(WindowCounterRow))).used,8)
            self.assertEqual((await db.get(UsageInboxRow,usage.measurement_id)).payload['prompt_tokens'],7)
