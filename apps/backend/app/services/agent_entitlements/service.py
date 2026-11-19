"""Backend-owned authorization transactions. Network I/O never runs under these locks.

Callers use one session_scope transaction per operation. Owner -> grant ->
allocation/window is the fixed lock order for all quota mutations, including
reconciliation. Serializing an owner is intentional; no in-memory quota exists.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from agent_contracts.canonical import digest, request_digest_v1
from agent_contracts.signing import sign_claims
from agent_contracts.v2 import (
    Allocation, BudgetGrant, CallPermitRequest, CallPermitResponse, GrantBindingReceipt, PermitStart,
    TaskMeteringBinding, TaskMeteringBindingReceipt, VoidProof, WindowRef,
)
from app.models.agent_entitlements import (
    CallPermitRow, EntitlementAuditRow, EntitlementPolicyRow, GrantRevisionRow,
    GrantRootRow, MeteringProfileRow, OwnerEntitlementRow, ReservationAllocationRow,
    SubmissionRow, UsageLedgerRow, WindowCounterRow,
)
from .policy import EntitlementPolicy


def now_utc():
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def uid():
    return uuid.uuid4().hex


class EntitlementError(Exception):
    def __init__(self, reason: str, status: int = 409, retryable: bool = False):
        self.reason, self.status, self.retryable = reason, status, retryable
        super().__init__(reason)


def require(condition, reason='AUTHORIZATION_CONFLICT', status=409):
    if not condition:
        raise EntitlementError(reason, status)


class Entitlements:
    def __init__(self, *, issuer: str, audience: str, kid: str | None = None,
                 private_key=None, allow_test_policy=False):
        self.issuer, self.audience = issuer, audience
        self.kid, self.private_key = kid, private_key
        self.allow_test_policy = allow_test_policy

    async def owner(self, db, owner_id, *, active=True):
        owner = await db.scalar(select(OwnerEntitlementRow).where(
            OwnerEntitlementRow.owner_id == owner_id).with_for_update())
        require(owner is not None and (owner.enabled or not active), 'ENTITLEMENT_UNAVAILABLE', 403)
        return owner

    async def policy(self, db, owner):
        row = await db.get(EntitlementPolicyRow, owner.policy_revision)
        require(row is not None and row.approved and (not row.test_only or self.allow_test_policy),
                'POLICY_NOT_APPROVED', 403)
        return EntitlementPolicy.model_validate(row.payload)

    async def lock_grant(self, db, grant_id):
        # Lookup identifies the owner only; all checks are repeated under locks.
        root = await db.get(GrantRootRow, grant_id)
        require(root is not None, 'GRANT_NOT_FOUND', 404)
        submission = await db.get(SubmissionRow, root.submission_id)
        owner = await self.owner(db, submission.owner_id, active=False)
        root = await db.scalar(select(GrantRootRow).where(
            GrantRootRow.grant_id == grant_id).with_for_update().execution_options(populate_existing=True))
        revision = await db.get(GrantRevisionRow, (grant_id, root.current_revision))
        grant = BudgetGrant.model_validate(revision.payload)
        return owner, root, grant

    def sign(self, claims, model):
        require(self.private_key is not None and self.kid is not None, 'SIGNING_UNAVAILABLE', 503)
        return sign_claims(claims, model, kid=self.kid, private_key=self.private_key)

    async def ledger(self, db, *, owner, root, allocation, key, kind, held=0, used=0,
                     measurement=None, evidence=None):
        db.add(UsageLedgerRow(entry_id=uid(), operation_key=key, owner_id=owner,
                             grant_id=root.grant_id, allocation_id=allocation,
                             measurement_id=measurement, kind=kind,
                             held_delta=held, used_delta=used, evidence=evidence or {}, created_at=now_utc()))

    async def prepare_profile(self, db, *, owner_id, request_digest, admission_revision,
                              context='observation_only', submission_id=None, client_key=None):
        require(context == 'observation_only' or submission_id is not None, 'INVALID_METERING_CONTEXT')
        row = MeteringProfileRow(profile_id=uid(), owner_id=owner_id, audience=self.audience,
                                 context=context, provenance='a1_admission' if context == 'observation_only' else 'authorized_submission',
                                 admission_revision=admission_revision, request_digest=request_digest,
                                 client_key=client_key,
                                 backend_submission_id=submission_id, enrollment_at=now_utc())
        db.add(row)
        await db.flush()
        return row

    async def bind_metering(self, db, body: TaskMeteringBinding):
        profile = await db.scalar(select(MeteringProfileRow).where(
            MeteringProfileRow.profile_id == body.metering_profile_id).with_for_update())
        require(profile is not None, 'METERING_PROFILE_NOT_FOUND', 404)
        require((profile.owner_id, profile.audience, profile.request_digest) ==
                (body.owner_id, body.agent_audience, body.request_digest), 'METERING_BINDING_CONFLICT')
        authorized = profile.context == 'authorized'
        require(body.submission_id_source == ('backend' if authorized else 'agent_observation'), 'METERING_MODE_CONFLICT')
        require(body.submission_id.startswith('obs:') != authorized, 'SUBMISSION_NAMESPACE_CONFLICT')
        if authorized:
            require(profile.backend_submission_id == body.submission_id, 'SUBMISSION_CONFLICT')
        if profile.binding:
            receipt = TaskMeteringBindingReceipt.model_validate(profile.binding)
            require((receipt.task_id, receipt.submission_id) == (body.task_id, body.submission_id), 'METERING_BINDING_CONFLICT')
            return receipt
        profile.task_id = body.task_id
        if not authorized:
            profile.observation_submission_id = body.submission_id
        receipt = TaskMeteringBindingReceipt(schema_version=1,
            metering_profile_id=profile.profile_id, task_id=body.task_id, metering_context=profile.context,
            submission_id_source=body.submission_id_source, submission_id=body.submission_id,
            bound_at=now_utc(), admission_revision=profile.admission_revision)
        profile.binding = receipt.model_dump(mode='json')
        return receipt

    async def authorize_submission(self, db: AsyncSession, *, owner_id: str,
                                   client_key: str, request: dict, client_request_digest=None):
        require(bool(client_key), 'IDEMPOTENCY_KEY_REQUIRED', 422)
        owner = await self.owner(db, owner_id)
        request_digest = request_digest_v1(request)
        existing = await db.scalar(select(SubmissionRow).where(
            SubmissionRow.owner_id == owner_id, SubmissionRow.client_key == client_key))
        if existing:
            require(existing.request_digest == request_digest and existing.request == request, 'IDEMPOTENCY_CONFLICT')
            require(client_request_digest is None or existing.client_request_digest == client_request_digest, 'IDEMPOTENCY_CONFLICT')
            root = await db.scalar(select(GrantRootRow).where(GrantRootRow.submission_id == existing.submission_id))
            rev = await db.get(GrantRevisionRow, (root.grant_id, root.current_revision))
            return existing, BudgetGrant.model_validate(rev.payload)
        policy = await self.policy(db, owner)
        require(owner.plan_id == policy.plan_id, 'PLAN_POLICY_CONFLICT', 403)
        require(request.get('owner_id') == owner_id, 'OWNER_CONFLICT', 403)
        submission_id = uid()
        profile = await self.prepare_profile(db, owner_id=owner_id, request_digest=request_digest,
                                             admission_revision=policy.policy_revision,
                                             context='authorized', submission_id=submission_id, client_key=client_key)
        submission = SubmissionRow(submission_id=submission_id, owner_id=owner_id, client_key=client_key,
                                   request_digest=request_digest, request=request, client_request_digest=client_request_digest,
                                   profile_id=profile.profile_id,
                                   status='prepared', created_at=now_utc())
        db.add(submission)
        await db.flush()
        root = GrantRootRow(grant_id=uid(), submission_id=submission_id, reservation_id=uid(),
                            current_revision=1, binding_revision=0, status='issued', settlement_status='held', overage=False)
        db.add(root)
        await db.flush()
        allocations = []
        now = now_utc()
        for rule in sorted(policy.rules, key=lambda r: r.rule_id):
            window = rule.window(owner_id, policy.policy_revision, now)
            counter = await db.get(WindowCounterRow, window.window_id)
            if counter is None:
                counter = WindowCounterRow(window_id=window.window_id, owner_id=owner_id, rule_id=rule.rule_id,
                                           window_ref=window.model_dump(mode='json'), limit_units=rule.limit_units, held=0, used=0)
                db.add(counter)
                await db.flush()
            await self.refresh_rolling(db, counter, now)
            require(counter.used + counter.held + rule.reservation_units <= counter.limit_units, 'QUOTA_EXHAUSTED', 403)
            allocation = Allocation(schema_version=1, allocation_id=uid(), rule_id=rule.rule_id, metric=rule.metric,
                                    unit=rule.unit, scope='owner_window' if rule.capability_id is None else 'capability_window',
                                    capability_id=rule.capability_id, purpose=rule.purpose,
                                    reserved_units=rule.reservation_units, window_ref=window)
            allocations.append(allocation)
            db.add(ReservationAllocationRow(allocation_id=allocation.allocation_id, grant_id=root.grant_id,
                                           window_id=window.window_id, allocation=allocation.model_dump(mode='json'),
                                           task_held=rule.reservation_units))
            counter.held += rule.reservation_units
            await db.flush()
            await self.ledger(db, owner=owner_id, root=root, allocation=allocation.allocation_id,
                              key=f'reserve:{allocation.allocation_id}', kind='held', held=rule.reservation_units)
        grant = self.sign(dict(
            schema_version=1, grant_id=root.grant_id, reservation_id=root.reservation_id, revision=1,
            issuer=self.issuer, audience=self.audience, owner_id=owner_id, submission_id=submission_id,
            task_id=None, binding_receipt_id=None, request_digest=request_digest, digest_profile='canonical_json_v1',
            policy_revision=policy.policy_revision, catalog_revision=policy.permission_snapshot.catalog_revision,
            permission_snapshot_id=policy.permission_snapshot.permission_snapshot_id,
            permission_snapshot_digest=digest(policy.permission_snapshot.model_dump(mode='json')),
            issued_at=now, not_before=now, expires_at=now + timedelta(seconds=policy.grant_ttl_seconds),
            capabilities=[c.model_dump(mode='json') for c in policy.permission_snapshot.capabilities],
            allocations=[a.model_dump(mode='json') for a in allocations], execution_constraints={}), BudgetGrant)
        db.add(GrantRevisionRow(grant_id=root.grant_id, revision=1, payload=grant.model_dump(mode='json'),
                               payload_digest=digest(grant.model_dump(mode='json', exclude={'signature'}))))
        return submission, grant

    async def refresh_rolling(self, db, counter, now):
        window = WindowRef.model_validate(counter.window_ref)
        if window.window_type != 'rolling':
            return
        # Signed deltas retain trusted-start attribution even when revised later.
        entries = (await db.scalars(select(UsageLedgerRow).join(
            ReservationAllocationRow, UsageLedgerRow.allocation_id == ReservationAllocationRow.allocation_id
        ).where(ReservationAllocationRow.window_id == counter.window_id))).all()
        cutoff = now - timedelta(seconds=window.duration_seconds)
        used = 0
        for entry in entries:
            started = entry.evidence.get('started_at')
            if started and datetime.fromisoformat(started.replace('Z', '+00:00')) > cutoff:
                used += entry.used_delta
        counter.used = max(used, 0)

    async def bind_grant(self, db, *, grant_id, task_id, owner_id, submission_id,
                         request_digest, expected_revision, expected_binding_revision):
        owner, root, grant = await self.lock_grant(db, grant_id)
        require((owner.owner_id, root.submission_id, grant.request_digest) ==
                (owner_id, submission_id, request_digest), 'GRANT_BINDING_CONFLICT')
        require(root.status not in ('revoked', 'closed') and now_utc() < grant.expires_at, 'GRANT_INACTIVE', 403)
        if root.receipt:
            require(root.bound_task_id == task_id, 'GRANT_BINDING_CONFLICT')
            return GrantBindingReceipt.model_validate(root.receipt)
        require(root.current_revision == expected_revision and root.binding_revision == expected_binding_revision == 0,
                'GRANT_REVISION_CONFLICT')
        rev = await db.get(GrantRevisionRow, (grant_id, expected_revision))
        receipt = self.sign(dict(schema_version=1, receipt_id=uid(), issuer=self.issuer, audience=self.audience,
                                 grant_id=grant_id, grant_revision=expected_revision, grant_payload_digest=rev.payload_digest,
                                 reservation_id=root.reservation_id, owner_id=owner_id, submission_id=submission_id,
                                 bound_task_id=task_id, request_digest=request_digest, bound_at=now_utc(), binding_revision=1),
                            GrantBindingReceipt)
        root.bound_task_id, root.binding_revision, root.receipt, root.status = task_id, 1, receipt.model_dump(mode='json'), 'active'
        return receipt

    async def revoke(self, db, grant_id, operation_id, principal, reason, *, capability_id=None, capability_version=None):
        owner, root, grant = await self.lock_grant(db, grant_id)
        policy_row = await db.get(EntitlementPolicyRow, grant.policy_revision)
        policy = EntitlementPolicy.model_validate(policy_row.payload)
        scoped = policy.emergency_scope == 'grant_capability'
        require((capability_id is not None and capability_version is not None) if scoped else
                capability_id is None and capability_version is None, 'REVOCATION_SCOPE_CONFLICT')
        old = await db.scalar(select(EntitlementAuditRow).where(EntitlementAuditRow.operation_id == operation_id))
        payload = {'grant_id': grant_id, 'action': 'revoke', 'reason': reason,
                   'capability_id': capability_id, 'capability_version': capability_version}
        if old:
            require(old.payload == payload and old.principal == principal, 'IDEMPOTENCY_CONFLICT')
            return
        require(root.status != 'closed', 'GRANT_CLOSED')
        if scoped:
            require(any(p.capability_id == capability_id and p.capability_version == capability_version
                        for p in grant.capabilities), 'CAPABILITY_NOT_AUTHORIZED')
            pair = [capability_id, capability_version]
            if pair not in root.revoked_capabilities:
                root.revoked_capabilities = [*root.revoked_capabilities, pair]
        else:
            root.status = 'revoked'
            root.settlement_status = 'draining'
        db.add(EntitlementAuditRow(audit_id=uid(), operation_id=operation_id, principal=principal,
                                   reason=reason, payload=payload, created_at=now_utc()))

    async def revise(self, db, grant_id, *, expected_revision, expected_binding_revision, expires_at):
        owner, root, previous = await self.lock_grant(db, grant_id)
        require(root.status not in ('revoked', 'closed'), 'GRANT_INACTIVE', 403)
        require((root.current_revision, root.binding_revision) == (expected_revision, expected_binding_revision), 'GRANT_REVISION_CONFLICT')
        # Revisions do not create balances or silently widen permissions.
        claims = previous.model_dump(mode='python', exclude={'signature'})
        claims.update(revision=expected_revision + 1, issued_at=now_utc(), expires_at=expires_at,
                      task_id=root.bound_task_id, binding_receipt_id=root.receipt['receipt_id'] if root.receipt else None)
        grant = self.sign(claims, BudgetGrant)
        root.current_revision += 1
        db.add(GrantRevisionRow(grant_id=grant_id, revision=root.current_revision, payload=grant.model_dump(mode='json'),
                               payload_digest=digest(grant.model_dump(mode='json', exclude={'signature'}))))
        return grant

    async def permit(self, db, request: CallPermitRequest):
        owner, root, grant = await self.lock_grant(db, request.grant_id)
        old = await db.scalar(select(CallPermitRow).where(CallPermitRow.audience == self.audience,
                                                         CallPermitRow.call_id == request.call_id))
        raw = request.model_dump(mode='json')
        if old:
            require(old.request == raw, 'CALL_ID_CONFLICT')
            return old.response
        reason = None
        policy_row = await db.get(EntitlementPolicyRow, grant.policy_revision)
        require(policy_row is not None and policy_row.approved and (not policy_row.test_only or self.allow_test_policy), 'POLICY_NOT_APPROVED', 403)
        policy = EntitlementPolicy.model_validate(policy_row.payload)
        now = now_utc()
        if not owner.enabled or root.status != 'active' or root.overage or not grant.not_before <= now < grant.expires_at:
            reason = 'GRANT_INACTIVE'
        elif (request.owner_id, request.submission_id, request.reservation_id, request.task_id,
              request.binding_receipt_id, request.grant_revision) != (
              owner.owner_id, root.submission_id, root.reservation_id, root.bound_task_id,
              root.receipt['receipt_id'] if root.receipt else None, root.current_revision):
            reason = 'GRANT_BINDING_CONFLICT'
        permission = next((p for p in grant.capabilities if (p.capability_id, p.capability_version) ==
                           (request.capability_id, request.capability_version)), None)
        if permission is None or request.invocation_mode not in permission.invocation_modes or request.purpose not in permission.purposes:
            reason = reason or 'CAPABILITY_NOT_AUTHORIZED'
        if [request.capability_id, request.capability_version] in root.revoked_capabilities:
            reason = reason or 'CAPABILITY_REVOKED'
        allowed_versions = {(p.capability_id, p.capability_version) for p in grant.capabilities
                            if [p.capability_id, p.capability_version] not in root.revoked_capabilities}
        if permission and any((k, v) not in allowed_versions for k, v in permission.dependency_versions.items()):
            reason = reason or 'DEPENDENCY_NOT_AUTHORIZED'
        if permission and permission.max_attempts is not None:
            count = await db.scalar(select(func.count()).select_from(CallPermitRow).where(
                CallPermitRow.grant_id == root.grant_id,
                CallPermitRow.request['capability_id'].as_string() == request.capability_id,
                CallPermitRow.state.not_in(('denied', 'void'))))
            if count >= permission.max_attempts:
                reason = reason or 'CAPABILITY_LIMIT_EXHAUSTED'
        if request.purpose in ('main', 'summary'):
            # Opaque Worker evidence references alone cannot prove token bounds.
            # Until a trusted tokenizer/bound verifier is installed, only an
            # explicitly approved risk policy can admit this provider.
            if policy.model_risk_profile is None or request.risk_profile != policy.model_risk_profile:
                reason = reason or 'TOKEN_BOUND_UNPROVEN'
        applicable = [a for a in grant.allocations if (a.capability_id is None or a.capability_id == request.capability_id)
                      and a.purpose in ('all', request.purpose)
                      and (a.unit == 'token' and request.purpose in ('main', 'summary') or
                           a.unit == 'activation' and request.purpose == 'skill_activation' or
                           a.unit == 'call' and request.purpose != 'skill_activation')]
        requested = {a.allocation_id: a for a in request.requested_allocations}
        if len(requested) != len(request.requested_allocations) or set(requested) != {a.allocation_id for a in applicable}:
            reason = reason or 'ALLOCATION_MISMATCH'
        held = {}
        deadlines = [now + timedelta(seconds=policy.permit_ttl_seconds), grant.expires_at]
        for a in applicable:
            requested_a = requested.get(a.allocation_id)
            allocation = await db.get(ReservationAllocationRow, a.allocation_id)
            rule = next(r for r in policy.rules if r.rule_id == a.rule_id)
            if requested_a is None or (requested_a.metric, requested_a.unit) != (a.metric, a.unit):
                reason = reason or 'ALLOCATION_MISMATCH'
                continue
            units = requested_a.upper_bound_units
            if units > rule.call_upper_bound or units > allocation.task_held:
                reason = reason or 'QUOTA_EXHAUSTED'
            if a.window_ref.accounting_basis != 'free' and a.metric in ('attempted_units', 'successful_units') and units < 1:
                reason = reason or 'CALL_BOUND_INVALID'
            if a.window_ref.end is not None:
                deadlines.append(a.window_ref.end)
                if not a.window_ref.start <= now < a.window_ref.end:
                    reason = reason or 'WINDOW_CLOSED'
            held[a.allocation_id] = units
        require(bool(applicable), 'ALLOCATION_MISSING', 403)
        permit_id = uid()
        start_before = min(deadlines) - timedelta(milliseconds=policy.conservative_clock_skew_ms)
        if start_before <= now:
            reason = reason or 'START_DEADLINE_EXCEEDED'
        payload = dict(schema_version=1, permit_id=permit_id, status='authorized',
                       **{k: raw[k] for k in ('call_id', 'grant_id', 'grant_revision', 'owner_id', 'submission_id',
                                             'task_id', 'run_id', 'execution_id', 'capability_id', 'capability_version', 'invocation_mode', 'purpose')},
                       policy_revision=grant.policy_revision, issued_at=now.isoformat(), expires_at=min(deadlines).isoformat(),
                       start_before=start_before.isoformat(), allocations=[dict(a.model_dump(mode='json'), held_units=held.get(a.allocation_id, 0)) for a in applicable])
        response = dict(schema_version=1, call_id=request.call_id, request_digest=request.request_digest,
                        decision='denied' if reason else 'authorized', reason_code=reason, retryable=False,
                        current_grant_revision=root.current_revision, permit=None if reason else payload)
        response = CallPermitResponse.model_validate(response).model_dump(mode='json')
        db.add(CallPermitRow(permit_id=permit_id, audience=self.audience, call_id=request.call_id,
                             grant_id=root.grant_id, request_digest=digest(raw), request=raw, response=response,
                             state='denied' if reason else 'authorized', held={} if reason else held, adopted={}))
        if reason is None:
            for allocation_id, units in held.items():
                allocation = await db.get(ReservationAllocationRow, allocation_id)
                allocation.task_held -= units  # task-held -> call-held, no second window debit
        return response

    async def start(self, db, permit_id, operation: PermitStart):
        permit = await db.get(CallPermitRow, permit_id)
        require(permit is not None, 'PERMIT_NOT_FOUND', 404)
        owner, root, grant = await self.lock_grant(db, permit.grant_id)
        permit = await db.scalar(select(CallPermitRow).where(CallPermitRow.permit_id == permit_id)
                                 .with_for_update().execution_options(populate_existing=True))
        require((operation.execution_id, operation.control_attestation_id) ==
                (permit.request['execution_id'], permit.request['control_attestation_id']), 'EXECUTION_CONFLICT')
        if permit.start:
            require(permit.start['start_operation_id'] == operation.start_operation_id, 'START_OPERATION_CONFLICT')
            return {**permit.start, 'first_commit': False}
        require(owner.enabled and root.status == 'active' and not root.overage and grant.revision == permit.request['grant_revision'], 'GRANT_INACTIVE', 403)
        require(permit.state == 'authorized', 'PERMIT_NOT_STARTABLE', 403)
        require([permit.request['capability_id'], permit.request['capability_version']] not in root.revoked_capabilities,
                'CAPABILITY_REVOKED', 403)
        permission = next((p for p in grant.capabilities if (p.capability_id, p.capability_version) ==
                          (permit.request['capability_id'], permit.request['capability_version'])), None)
        require(permission is not None and all([k, v] not in root.revoked_capabilities
                for k, v in permission.dependency_versions.items()), 'DEPENDENCY_NOT_AUTHORIZED', 403)
        now = now_utc()
        limit = datetime.fromisoformat(permit.response['permit']['start_before'])
        policy_row = await db.get(EntitlementPolicyRow, grant.policy_revision)
        require(policy_row.approved and (not policy_row.test_only or self.allow_test_policy), 'POLICY_NOT_APPROVED', 403)
        policy = EntitlementPolicy.model_validate(policy_row.payload)
        require(policy.disable_scope != 'every_start' or owner.policy_revision == grant.policy_revision, 'POLICY_REVOKED', 403)
        require(grant.not_before <= now < min(limit, grant.expires_at), 'START_DEADLINE_EXCEEDED', 403)
        limit = min(limit, now + timedelta(seconds=policy.start_ttl_seconds))
        permit.state = 'start_committed'
        permit.start = dict(schema_version=1, start_operation_id=operation.start_operation_id,
                            start_authorization_id=uid(), committed_at=now.isoformat(), start_before=limit.isoformat())
        return {**permit.start, 'first_commit': True}

    async def void(self, db, proof: VoidProof):
        permit = await db.get(CallPermitRow, proof.permit_id)
        require(permit is not None, 'PERMIT_NOT_FOUND', 404)
        owner, root, grant = await self.lock_grant(db, permit.grant_id)
        permit = await db.scalar(select(CallPermitRow).where(CallPermitRow.permit_id == proof.permit_id)
                                 .with_for_update().execution_options(populate_existing=True))
        require((proof.call_id, proof.execution_id, proof.control_attestation_id) ==
                (permit.call_id, permit.request['execution_id'], permit.request['control_attestation_id']), 'VOID_PROOF_CONFLICT')
        raw = proof.model_dump(mode='json')
        if permit.void_proof:
            require(permit.void_proof == raw, 'VOID_PROOF_CONFLICT')
            return
        require(permit.state in ('authorized', 'start_committed', 'expired'), 'VOID_NOT_PROVEN')
        if permit.start:
            require((proof.start_operation_id, proof.backend_start_authorization_id) ==
                    (permit.start['start_operation_id'], permit.start['start_authorization_id']), 'VOID_PROOF_CONFLICT')
        for allocation_id, units in permit.held.items():
            allocation = await db.get(ReservationAllocationRow, allocation_id)
            # Return to task reserve, not spendable owner balance until task close.
            allocation.task_held += units
        permit.held, permit.state, permit.void_proof = {}, 'void', raw

    async def abandon_request(self, db, body):
        """Close a requesting intent whose permit response was lost.

        The durable Control seal proves no local start operation ever existed.
        A root-locked tombstone also serializes an in-flight authorize request:
        a later delivery of that original request can never create spending power.
        """
        request = body.request
        owner, root, grant = await self.lock_grant(db, request.grant_id)
        require((request.owner_id, request.submission_id, request.reservation_id, request.task_id) ==
                (owner.owner_id, root.submission_id, root.reservation_id, root.bound_task_id), 'CALL_IDENTITY_CONFLICT')
        old = await db.scalar(select(CallPermitRow).where(CallPermitRow.audience == self.audience,
                                                         CallPermitRow.call_id == request.call_id).with_for_update())
        raw = request.model_dump(mode='json')
        proof = body.model_dump(mode='json')
        if old:
            require(old.request == raw, 'CALL_ID_CONFLICT')
            if old.void_proof:
                require(old.void_proof == proof, 'VOID_PROOF_CONFLICT')
            else:
                require(old.start is None and old.state in ('authorized', 'expired', 'denied'), 'VOID_NOT_PROVEN')
                for allocation_id, units in old.held.items():
                    allocation = await db.get(ReservationAllocationRow, allocation_id)
                    allocation.task_held += units
                old.held, old.state, old.void_proof = {}, 'void', proof
        else:
            response = CallPermitResponse(schema_version=1, call_id=request.call_id, request_digest=request.request_digest,
                decision='denied', reason_code='CALL_PERMANENTLY_SEALED', retryable=False,
                current_grant_revision=root.current_revision, permit=None).model_dump(mode='json')
            old = CallPermitRow(permit_id=uid(), audience=self.audience, call_id=request.call_id, grant_id=root.grant_id,
                request_digest=digest(raw), request=raw, response=response, state='void', held={}, adopted={}, void_proof=proof)
            db.add(old)
        return dict(schema_version=1, state='void', permit_id=old.permit_id, response=old.response)
