"""Durable Inbox, startup verification, append-only settlement and close checks."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from agent_contracts.canonical import digest
from agent_contracts.v2 import CallIdentity, CallStartFact, TaskCloseManifest, UsageAck, UsageDelta
from app.models.agent_entitlements import (
    CallPermitRow, EntitlementAuditRow, EntitlementPolicyRow, GrantRootRow, GrantRevisionRow, MeteringProfileRow,
    ReservationAllocationRow, SubmissionRow, TaskCloseRow, UsageInboxRow,
    UsageLedgerRow, UsageProjectionRow, WindowCounterRow,
)
from .policy import EntitlementPolicy
from .service import Entitlements, now_utc, require, uid


def identity_payload(value):
    return {k: value.model_dump(mode='json')[k] for k in CallIdentity.model_fields}


class UsageSettlement:
    def __init__(self, entitlements: Entitlements):
        self.entitlements = entitlements

    async def ingest(self, db, usage: UsageDelta, fact: CallStartFact | None,
                     *, verification_error=None, principal='agent-control') -> UsageAck:
        """fact is fetched through the trusted Gateway before entering this transaction.

        Query failures still produce durable quarantined receipts. Reprocessing
        takes the original measurement_id; raw Inbox content is never updated.
        """
        raw = usage.model_dump(mode='json')
        root = grant = owner = None
        if usage.metering_context == 'authorized':
            root_exists = await db.get(GrantRootRow, usage.grant_id)
            if root_exists:
                owner, root, grant = await self.entitlements.lock_grant(db, usage.grant_id)
        profile = await db.scalar(select(MeteringProfileRow).where(
            MeteringProfileRow.profile_id == usage.metering_profile_id).with_for_update())
        existing = await db.get(UsageInboxRow, usage.measurement_id)
        occupied = await db.scalar(select(UsageInboxRow).where(
            ((UsageInboxRow.call_id == usage.call_id) & (UsageInboxRow.revision == usage.observation_revision)) |
            ((UsageInboxRow.task_id == usage.task_id) & (UsageInboxRow.sequence == usage.task_usage_sequence))))
        conflict = ((existing is not None and existing.content_digest != digest(raw)) or
                    (occupied is not None and occupied.measurement_id != usage.measurement_id))
        if conflict:
            db.add(EntitlementAuditRow(audit_id=uid(), operation_id=uid(), principal=principal,
                                       reason='USAGE_IDENTITY_CONFLICT', payload=raw, created_at=now_utc()))
            if root:
                root.settlement_status = 'reconciliation_required'
            return self.ack(usage, disposition='rejected', durable=False, reason='USAGE_IDENTITY_CONFLICT')
        inbox = existing
        if inbox is None:
            inbox = UsageInboxRow(measurement_id=usage.measurement_id, call_id=usage.call_id,
                                  task_id=usage.task_id, revision=usage.observation_revision,
                                  sequence=usage.task_usage_sequence, payload=raw, content_digest=digest(raw),
                                  verification_status='pending', received_at=now_utc())
            db.add(inbox)
            await db.flush()
        projection = await db.get(UsageProjectionRow, usage.call_id)
        if existing is not None and existing.verification_status == 'verified':
            return await self.receipt(db, usage, projection, 'duplicate')
        reason = verification_error
        if profile is None or (profile.owner_id, profile.audience, profile.task_id, profile.context) != (
                usage.owner_id, usage.agent_audience, usage.task_id, usage.metering_context):
            reason = 'METERING_BINDING_UNVERIFIED'
        elif (profile.backend_submission_id if profile.context == 'authorized' else profile.observation_submission_id) != usage.submission_id:
            reason = 'SUBMISSION_BINDING_CONFLICT'
        elif profile.enrollment_at.replace(tzinfo=timezone.utc) > usage.started_at:
            reason = 'FACT_BEFORE_ENROLLMENT'
        if fact is None:
            reason = reason or 'START_FACT_UNAVAILABLE'
        elif identity_payload(fact) != identity_payload(usage) or fact.computed_digest() != fact.start_record_digest:
            reason = 'START_FACT_CONFLICT'
        elif projection and projection.start_fact != fact.model_dump(mode='json'):
            reason = 'START_FACT_CHANGED'
        if usage.metering_context == 'authorized':
            permit = await db.get(CallPermitRow, usage.permit_id)
            if (root is None or permit is None or not permit.start or permit.state in ('void', 'denied') or
                    root.bound_task_id != usage.task_id or root.submission_id != usage.submission_id or
                    root.reservation_id != usage.reservation_id or permit.call_id != usage.call_id):
                reason = 'PERMIT_START_UNVERIFIED'
            elif any(permit.request[k] != raw[k] for k in (
                    'owner_id', 'submission_id', 'task_id', 'run_id', 'execution_id', 'control_attestation_id',
                    'grant_id', 'grant_revision', 'reservation_id', 'capability_id', 'capability_version',
                    'invocation_mode', 'purpose', 'logical_call_id')):
                reason = 'PERMIT_IDENTITY_CONFLICT'
            elif not (datetime.fromisoformat(permit.start['committed_at']) <= usage.started_at <
                      datetime.fromisoformat(permit.start['start_before'])):
                reason = 'START_TIME_CONFLICT'
        # Check both neighbors; a late predecessor may expose a forged chain.
        neighbors = (await db.scalars(select(UsageInboxRow).where(UsageInboxRow.call_id == usage.call_id))).all()
        for n in neighbors:
            if identity_payload(UsageDelta.model_validate(n.payload)) != identity_payload(usage):
                reason = 'CALL_IMMUTABLE_IDENTITY_CONFLICT'
            if n.revision == usage.observation_revision - 1 and n.measurement_id != usage.supersedes_measurement_id:
                reason = 'OBSERVATION_CHAIN_CONFLICT'
            if n.revision == usage.observation_revision + 1 and n.payload['supersedes_measurement_id'] != usage.measurement_id:
                reason = 'OBSERVATION_CHAIN_CONFLICT'
        if reason:
            inbox.verification_status, inbox.reason = 'quarantined', reason
            if root:
                root.settlement_status = 'reconciliation_required'
            return self.ack(usage, disposition='quarantined', durable=True, reason=reason,
                            revision=projection.revision if projection else None)
        inbox.verification_status, inbox.reason = 'verified', None
        db.add(EntitlementAuditRow(audit_id=uid(), operation_id=uid(), principal=principal,
                                   reason='START_FACT_VERIFIED', payload={
                                       'measurement_id': usage.measurement_id, 'call_id': usage.call_id,
                                       'start_record_digest': fact.start_record_digest}, created_at=now_utc()))
        if projection is None or usage.observation_revision > projection.revision:
            if root and root.status == 'closed':
                root.settlement_status = 'reconciliation_required'
            if root:
                await self.settle(db, owner.owner_id, root, usage)
            status = ('not_applicable' if root is None else
                      'settled' if usage.usage_status == 'measured' and usage.phase != 'started' else 'reconciliation_required')
            if projection is None:
                projection = UsageProjectionRow(call_id=usage.call_id, task_id=usage.task_id,
                    revision=usage.observation_revision, payload=raw, start_fact=fact.model_dump(mode='json'), settlement_status=status)
                db.add(projection)
            else:
                projection.revision, projection.payload, projection.settlement_status = usage.observation_revision, raw, status
        await db.flush()
        return await self.receipt(db, usage, projection, 'accepted')

    def ack(self, usage, *, disposition, durable, reason=None, revision=None, status='pending', missing_revisions=(), missing_sequences=()):
        return UsageAck(schema_version=1, measurement_id=usage.measurement_id, call_id=usage.call_id,
                        observation_revision=usage.observation_revision, disposition=disposition,
                        durable=durable, applied_revision=revision, settlement_status=status,
                        reason_code=reason, retryable=durable and disposition == 'quarantined', retry_after_ms=None,
                        missing_revisions=list(missing_revisions), missing_sequences=list(missing_sequences))

    async def receipt(self, db, usage, projection, disposition):
        revisions = set((await db.scalars(select(UsageInboxRow.revision).where(UsageInboxRow.call_id == usage.call_id))).all())
        sequences = set((await db.scalars(select(UsageInboxRow.sequence).where(UsageInboxRow.task_id == usage.task_id))).all())
        # Gaps are reported without allocating an attacker-controlled huge range.
        def missing(values):
            found, prior = [], 0
            for v in sorted(values):
                found.extend(range(prior + 1, min(v, prior + 201 - len(found))))
                prior = v
                if len(found) >= 200:
                    break
            return found
        gaps_r, gaps_s = missing(revisions), missing(sequences)
        return self.ack(usage, disposition=disposition, durable=True,
                        revision=projection.revision if projection else None,
                        status='pending' if gaps_r or gaps_s else projection.settlement_status,
                        missing_revisions=gaps_r, missing_sequences=gaps_s)

    async def settle(self, db, owner, root, usage):
        revision = await db.get(GrantRevisionRow, (root.grant_id, usage.grant_revision))
        policy_row = await db.get(EntitlementPolicyRow, revision.payload['policy_revision'])
        policy = EntitlementPolicy.model_validate(policy_row.payload)
        permit = await db.get(CallPermitRow, usage.permit_id)
        adopted = dict(permit.adopted)
        held = dict(permit.held)
        for allocation_id in sorted(held):
            allocation = await db.get(ReservationAllocationRow, allocation_id)
            counter = await db.get(WindowCounterRow, allocation.window_id)
            metric = allocation.allocation['metric']
            if allocation.allocation['window_ref']['accounting_basis'] == 'free':
                continue  # explicit approved noncharging rule; raw usage stays intact
            if metric == 'tokens':
                # Partial measurements have a known lower bound, not a full zero.
                parts = (usage.prompt_tokens, usage.completion_tokens)
                if policy.token_scope == 'prompt_only':
                    parts = (usage.prompt_tokens,)
                elif policy.token_scope == 'completion_only':
                    parts = (usage.completion_tokens,)
                value = sum(v for v in parts if v is not None) if any(v is not None for v in parts) else None
                certain = usage.usage_status == 'measured' and None not in parts
            else:
                value = getattr(usage, metric)
                certain = value is not None and usage.phase != 'started'
            if value is None or usage.usage_status == 'estimated':
                await self.entitlements.ledger(db, owner=owner, root=root, allocation=allocation_id,
                    key=f'reconcile:{usage.measurement_id}:{allocation_id}', kind='reconciliation_required',
                    measurement=usage.measurement_id, evidence={'usage_status': usage.usage_status})
                continue  # unapproved estimated charges retain held
            prior = adopted.get(allocation_id, 0)
            difference = value - prior
            old_held = held[allocation_id]
            original_bound = next(a['held_units'] for a in permit.response['permit']['allocations'] if a['allocation_id'] == allocation_id)
            target_held = 0 if certain else max(original_bound - value, 0)
            await self.entitlements.refresh_rolling(db, counter, now_utc())
            # Complete historical usage is always retained, including overage.
            window = allocation.allocation['window_ref']
            in_window = (window['window_type'] != 'rolling' or usage.started_at >
                         now_utc() - timedelta(seconds=window['duration_seconds']))
            if in_window:
                counter.used += difference
            counter.held += target_held - old_held
            held[allocation_id], adopted[allocation_id] = target_held, value
            if difference or target_held != old_held:
                await self.entitlements.ledger(db, owner=owner, root=root, allocation=allocation_id,
                    key=f'usage:{usage.measurement_id}:{allocation_id}', kind='used' if prior == 0 else 'adjustment',
                    held=target_held - old_held, used=difference, measurement=usage.measurement_id,
                    evidence={'started_at': usage.started_at.isoformat(), 'usage_status': usage.usage_status})
            if value > original_bound or counter.used + counter.held > counter.limit_units:
                root.overage = True
                root.settlement_status = 'reconciliation_required'
        permit.adopted, permit.held = adopted, held
        permit.state = 'completed' if usage.phase != 'started' and usage.usage_status == 'measured' else 'unknown'

    async def close(self, db, manifest: TaskCloseManifest):
        owner, root, grant = await self.entitlements.lock_grant(db, manifest.grant_id)
        raw = manifest.model_dump(mode='json')
        old = await db.get(TaskCloseRow, manifest.manifest_id)
        if old:
            require(old.payload == raw, 'CLOSE_MANIFEST_CONFLICT')
            return old.status
        require((manifest.owner_id, manifest.submission_id, manifest.task_id, manifest.agent_audience) ==
                (owner.owner_id, root.submission_id, root.bound_task_id, self.entitlements.audience), 'CLOSE_IDENTITY_CONFLICT')
        root.settlement_status = 'draining'
        complete = await self.close_complete(db, manifest, root)
        policy_row = await db.get(EntitlementPolicyRow, grant.policy_revision)
        policy = EntitlementPolicy.model_validate(policy_row.payload)
        status = 'reconciliation_required'
        if complete and not root.overage and policy_row.approved and policy.unused_release_strategy == 'sealed_complete_only':
            allocations = (await db.scalars(select(ReservationAllocationRow).where(
                ReservationAllocationRow.grant_id == root.grant_id).order_by(ReservationAllocationRow.allocation_id))).all()
            for allocation in allocations:
                units = allocation.task_held
                if units:
                    counter = await db.get(WindowCounterRow, allocation.window_id)
                    counter.held -= units
                    allocation.task_held = 0
                    await self.entitlements.ledger(db, owner=owner.owner_id, root=root, allocation=allocation.allocation_id,
                        key=f'close:{root.grant_id}:{allocation.allocation_id}', kind='released', held=-units,
                        evidence={'manifest_id': manifest.manifest_id})
            root.status = 'closed'
            status = 'settled'
        root.settlement_status = status
        db.add(TaskCloseRow(manifest_id=manifest.manifest_id, grant_id=root.grant_id, payload=raw, status=status))
        return status

    async def close_complete(self, db, manifest, root):
        """Re-evaluate live settlement rows; never trust a cached close status."""
        permits = (await db.scalars(select(CallPermitRow).where(CallPermitRow.grant_id == root.grant_id,
                                                              CallPermitRow.state != 'denied'))).all()
        permits = [p for p in permits if p.response.get('permit') is not None]
        inbox = (await db.scalars(select(UsageInboxRow).where(UsageInboxRow.task_id == manifest.task_id))).all()
        projections = (await db.scalars(select(UsageProjectionRow).where(UsageProjectionRow.task_id == manifest.task_id))).all()
        sequences = sorted(i.sequence for i in inbox)
        complete = (len(sequences) == manifest.last_task_usage_sequence and
                    all(v == i + 1 for i, v in enumerate(sequences)))
        revisions = {}
        for i in inbox:
            revisions.setdefault(i.call_id, []).append(i.revision)
        complete = complete and all(sorted(v) == list(range(1, max(v) + 1)) for v in revisions.values())
        calls = {p.call_id for p in projections}
        unknown = {p.call_id for p in projections if p.settlement_status not in ('settled', 'adjusted')}
        started = [p for p in permits if p.start and p.state != 'void']
        complete = complete and all(i.verification_status == 'verified' for i in inbox)
        complete = complete and set(manifest.permit_ids) == {p.permit_id for p in permits}
        complete = complete and set(manifest.call_ids) == calls == {p.call_id for p in started}
        complete = complete and manifest.call_count == len(calls) and len(manifest.call_ids) == len(calls)
        complete = complete and set(manifest.run_ids) >= {p.request['run_id'] for p in permits}
        complete = complete and set(manifest.execution_ids) >= {p.request['execution_id'] for p in permits}
        complete = complete and manifest.all_executions_sealed and manifest.no_startable_permits
        complete = complete and not unknown and not manifest.unknown_call_ids and not manifest.missing_sequences
        complete = complete and manifest.outbox_ack_high_watermark == manifest.last_task_usage_sequence
        complete = complete and all(p.state in ('void', 'completed') and not any(p.held.values()) for p in permits)
        return complete

    async def task_usage(self, db, *, task_id, owner_id):
        profile = await db.scalar(select(MeteringProfileRow).where(MeteringProfileRow.task_id == task_id,
                                                                 MeteringProfileRow.owner_id == owner_id))
        require(profile is not None, 'TASK_NOT_FOUND', 404)
        if profile.context == 'authorized':
            await self.entitlements.owner(db, owner_id, active=False)
        else:
            profile = await db.scalar(select(MeteringProfileRow).where(MeteringProfileRow.profile_id == profile.profile_id)
                                       .with_for_update().execution_options(populate_existing=True))
        projections = (await db.scalars(select(UsageProjectionRow).where(UsageProjectionRow.task_id == task_id))).all()
        measured = estimated = known = 0
        unknown = 0
        counts = {}
        for p in projections:
            value = UsageDelta.model_validate(p.payload)
            total = sum(v for v in (value.prompt_tokens, value.completion_tokens) if v is not None)
            if value.usage_status == 'measured':
                measured += total
            elif value.usage_status == 'estimated':
                estimated += total
            known += total if value.usage_status != 'estimated' else 0
            unknown += value.usage_status in ('unknown', 'partial') or value.phase == 'started'
            counts[value.capability_id] = counts.get(value.capability_id, 0) + (value.attempted_units or 0)
        unverified = (await db.scalars(select(UsageInboxRow).where(UsageInboxRow.task_id == task_id,
                                                               UsageInboxRow.verification_status != 'verified'))).all()
        root = await db.scalar(select(GrantRootRow).where(GrantRootRow.submission_id == profile.backend_submission_id)) if profile.backend_submission_id else None
        ledger = (await db.scalars(select(UsageLedgerRow).where(UsageLedgerRow.grant_id == root.grant_id))).all() if root else []
        by_allocation = {}
        for entry in ledger:
            item = by_allocation.setdefault(entry.allocation_id, {'reserved': 0, 'held': 0, 'used': 0, 'released': 0})
            item['held'] += entry.held_delta
            item['used'] += entry.used_delta
            if entry.kind == 'held':
                item['reserved'] += entry.held_delta
        for item in by_allocation.values():
            item['released'] = max(0, item['reserved'] - item['held'] - item['used'])
        return dict(schema_version=1, task_id=task_id, metering_context=profile.context,
                    authorization_status=root.status if root else 'not_applicable', known_tokens=known,
                    measured_tokens=measured, estimated_tokens=estimated, unknown_call_count=unknown,
                    capability_attempts=counts, allocations=by_allocation,
                    settlement_status=root.settlement_status if root else 'not_applicable',
                    complete=bool(root and root.settlement_status == 'settled'),
                    reconciliation_status='required' if unknown or estimated or unverified or (root and root.settlement_status == 'reconciliation_required') else 'clear',
                    unverified_observation_count=len(unverified))
