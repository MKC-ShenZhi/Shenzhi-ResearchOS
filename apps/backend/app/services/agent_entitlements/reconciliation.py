"""Explicit Admin reconciliation of historical overage, using live Agent facts."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from pydantic import ValidationError
from agent_contracts.canonical import digest
from agent_contracts.v2 import TaskCloseManifest, UsageDelta
from app.core.database import session_scope
from app.models.agent_entitlements import (
    CallPermitRow, EntitlementAuditRow, EntitlementPolicyRow, GrantRootRow,
    ReservationAllocationRow, SubmissionRow, TaskCloseRow, UsageInboxRow, UsageLedgerRow,
    UsageProjectionRow, WindowCounterRow,
)
from .admin import admin_lock, replay
from .policy import EntitlementPolicy
from .service import require, now_utc, uid, EntitlementError
from .usage import UsageSettlement


def request_payload(grant_id, body):
    return {'action': 'reconcile-close', 'grant_id': grant_id, **body.model_dump(mode='json')}


async def historical_carry(db, service, counter, ledger_used):
    """Recognize one evidenced legacy daily carry; never infer a balance patch.

    This deliberately rejects chains, duplicates and source activity after the
    assignment. The caller already holds the owner lock shared by settlements.
    """
    require(counter.rule_id == 'daily-tokens' and counter.window_ref['window_type'] == 'natural'
            and counter.window_ref['accounting_basis'] == 'trusted_start', 'WINDOW_USED_LEDGER_CONFLICT')
    audits = (await db.scalars(select(EntitlementAuditRow).where(EntitlementAuditRow.reason == 'assign'))).all()
    matches = []
    for audit in audits:
        carries = audit.payload.get('carried_window_usage', [])
        require(isinstance(carries, list), 'CARRY_AUDIT_INVALID')
        for carry in carries:
            if isinstance(carry, dict) and carry.get('target_window_id') == counter.window_id:
                matches.append((audit, carry))
    require(len(matches) == 1, 'CARRY_AUDIT_MISSING_OR_AMBIGUOUS')
    audit, carry = matches[0]
    amount = carry.get('used')
    require(type(amount) is int and amount > 0 and type(carry.get('held')) is int and carry['held'] == 0
            and counter.used == ledger_used + amount, 'CARRY_AMOUNT_CONFLICT')
    source = await db.get(WindowCounterRow, carry.get('source_window_id'))
    require(source and source.window_id != counter.window_id and source.owner_id == counter.owner_id
            and audit.payload.get('owner_id') == counter.owner_id and audit.principal
            and audit.payload.get('history_preserved') is True, 'CARRY_IDENTITY_CONFLICT')
    require(source.rule_id == counter.rule_id == carry.get('rule_id')
            and source.window_ref['rule_revision'] != counter.window_ref['rule_revision']
            and source.window_ref['rule_revision'] == audit.payload.get('source_policy_revision')
            and counter.window_ref['rule_revision'] == audit.payload.get('policy_revision')
            and all(source.window_ref.get(k) == counter.window_ref.get(k) for k in
                    ('window_type', 'accounting_basis', 'timezone', 'start', 'end')),
            'CARRY_WINDOW_CONFLICT')
    entries = (await db.scalars(select(UsageLedgerRow).join(ReservationAllocationRow,
        UsageLedgerRow.allocation_id == ReservationAllocationRow.allocation_id).where(
        ReservationAllocationRow.window_id == source.window_id))).all()
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    require(entries and all(e.owner_id == counter.owner_id and utc(e.created_at) <= utc(audit.created_at)
                            for e in entries), 'CARRY_SOURCE_CHANGED_OR_UNVERIFIED')
    require(source.used == amount == sum(e.used_delta for e in entries) and
            source.held == sum(e.held_delta for e in entries) == 0, 'CARRY_SOURCE_LEDGER_CONFLICT')
    allocations = (await db.scalars(select(ReservationAllocationRow).where(
        ReservationAllocationRow.window_id == source.window_id))).all()
    for allocation in allocations:
        root = await db.get(GrantRootRow, allocation.grant_id)
        submission = await db.get(SubmissionRow, root.submission_id) if root else None
        require(submission and submission.owner_id == counter.owner_id and root.status == 'closed'
                and root.settlement_status == 'settled' and allocation.task_held == 0,
                'CARRY_SOURCE_GRANT_UNSETTLED')
        require(allocation.allocation['metric'] == 'tokens' and allocation.allocation['rule_id'] == source.rule_id
                and allocation.allocation['window_ref'] == source.window_ref, 'CARRY_SOURCE_ALLOCATION_CONFLICT')
        own_entries = [e for e in entries if e.allocation_id == allocation.allocation_id]
        permits = (await db.scalars(select(CallPermitRow).where(CallPermitRow.grant_id == root.grant_id))).all()
        require(all(p.state in ('completed', 'void', 'denied') and not any(p.held.values()) for p in permits)
                and sum(e.held_delta for e in own_entries) == 0
                and all(e.grant_id == root.grant_id for e in own_entries)
                and sum(e.used_delta for e in own_entries) == sum(p.adopted.get(allocation.allocation_id, 0) for p in permits),
                'CARRY_SOURCE_SETTLEMENT_CONFLICT')
        closes = (await db.scalars(select(TaskCloseRow).where(TaskCloseRow.grant_id == root.grant_id,
                                                            TaskCloseRow.status == 'settled'))).all()
        complete = False
        for close in closes:
            manifest = TaskCloseManifest.model_validate(close.payload)
            if await UsageSettlement(service).close_complete(db, manifest, root):
                complete = True
                break
        require(complete, 'CARRY_SOURCE_CLOSE_INCOMPLETE')
    return {'audit_id': audit.audit_id, 'operation_id': audit.operation_id,
            'source_window_id': source.window_id, 'target_window_id': counter.window_id,
            'used': amount, 'source_ledger_entry_ids': [e.entry_id for e in entries]}


async def reconcile(grant_id, body, principal):
    from .config import entitlement_service
    from app.services.agent_gateway.v2 import AgentGatewayV2

    request = request_payload(grant_id, body)
    async with session_scope() as db:
        await admin_lock(db)
        old = await replay(db, body.operation_id, principal, request)
        if old is not None:
            return old
        root = await db.get(GrantRootRow, grant_id)
        require(root is not None and root.bound_task_id, 'BOUND_GRANT_REQUIRED')
        task_id = root.bound_task_id
    # Trusted environment only; no caller-provided evidence is accepted as facts.
    facts = await AgentGatewayV2().close_facts(task_id)
    async with session_scope() as db:
        return await apply(db, entitlement_service(), grant_id, body, principal, facts)


async def apply(db, service, grant_id, body, principal, facts):
    require(principal.startswith('local-admin:'), 'ADMIN_REQUIRED', 403)
    await admin_lock(db)
    request = request_payload(grant_id, body)
    old = await replay(db, body.operation_id, principal, request)
    if old is not None:
        return old
    owner, root, grant = await service.lock_grant(db, grant_id)
    # Savepoints retain a rejection audit while rolling back any tentative writes.
    try:
        async with db.begin_nested():
            result = await validate_and_close(db, service, owner, root, grant, body, facts)
    except EntitlementError as exc:
        result = {'eligible': False, 'reason': exc.reason, 'grant_id': grant_id, 'preview': body.preview}
    db.add(EntitlementAuditRow(audit_id=uid(), operation_id=body.operation_id, principal=principal,
        reason=body.reason, payload={'action': 'reconcile-close', 'request': request,
            'result': result, 'facts': facts}, created_at=now_utc()))
    return result


async def validate_and_close(db, service, owner, root, grant, body, facts):
    require(root.status == 'active' and root.overage, 'ACTIVE_HISTORICAL_OVERAGE_REQUIRED')
    require(facts.get('task_status') == 'completed', 'TASK_NOT_COMPLETED')
    try:
        manifest = TaskCloseManifest.model_validate(facts.get('manifest'))
    except ValidationError:
        require(False, 'CLOSE_FACTS_INVALID')
    require(timedelta(0) <= now_utc() - manifest.closed_at <= timedelta(seconds=30), 'CLOSE_FACTS_STALE')
    require((manifest.owner_id, manifest.grant_id, manifest.submission_id, manifest.task_id, manifest.agent_audience) ==
            (owner.owner_id, root.grant_id, root.submission_id, root.bound_task_id, service.audience), 'CLOSE_IDENTITY_CONFLICT')
    closes = (await db.scalars(select(TaskCloseRow).where(TaskCloseRow.grant_id == root.grant_id))).all()
    # A submitted manifest must describe exactly the same final call set/sequence.
    def content(value):
        return {k: v for k, v in value.items() if k not in ('manifest_id', 'closed_at')}
    raw = manifest.model_dump(mode='json')
    require(any(content(c.payload) == content(raw) for c in closes), 'FINAL_CLOSE_MANIFEST_NOT_SUBMITTED')
    require(await UsageSettlement(service).close_complete(db, manifest, root), 'CLOSE_INCOMPLETE_OR_CALLS_UNSETTLED')
    policy_row = await db.get(EntitlementPolicyRow, grant.policy_revision)
    require(policy_row and policy_row.approved, 'POLICY_NOT_APPROVED')
    policy = EntitlementPolicy.model_validate(policy_row.payload)
    require(policy.unused_release_strategy == 'sealed_complete_only', 'UNUSED_RELEASE_NOT_APPROVED')
    allocations = (await db.scalars(select(ReservationAllocationRow).where(
        ReservationAllocationRow.grant_id == root.grant_id).order_by(ReservationAllocationRow.allocation_id))).all()
    require(allocations, 'RESERVATION_ALLOCATIONS_MISSING')
    permits = (await db.scalars(select(CallPermitRow).where(CallPermitRow.grant_id == root.grant_id))).all()
    projections = (await db.scalars(select(UsageProjectionRow).where(UsageProjectionRow.task_id == root.bound_task_id))).all()
    # Verify latest immutable Inbox content, actual usage and adopted per-call charges.
    for projection in projections:
        usage = UsageDelta.model_validate(projection.payload)
        inbox = await db.get(UsageInboxRow, usage.measurement_id)
        require(inbox and inbox.content_digest == digest(projection.payload) and inbox.payload == projection.payload,
                'USAGE_PROJECTION_LEDGER_CONFLICT')
        observations = (await db.scalars(select(UsageInboxRow).where(UsageInboxRow.call_id == usage.call_id))).all()
        require(projection.revision == max(i.revision for i in observations) == usage.observation_revision,
                'LATEST_USAGE_NOT_SETTLED')
        permit = next((p for p in permits if p.permit_id == usage.permit_id), None)
        require(permit is not None and permit.call_id == usage.call_id, 'PERMIT_USAGE_CONFLICT')
        require(usage.usage_status == 'measured' and usage.phase != 'started', 'USAGE_NOT_FINAL')
        for allocation in allocations:
            aid = allocation.allocation_id
            if aid not in permit.held or allocation.allocation['window_ref']['accounting_basis'] == 'free':
                continue
            metric = allocation.allocation['metric']
            parts = ((usage.prompt_tokens,) if policy.token_scope == 'prompt_only' else
                     (usage.completion_tokens,) if policy.token_scope == 'completion_only' else
                     (usage.prompt_tokens, usage.completion_tokens)) if metric == 'tokens' else (getattr(usage, metric),)
            require(None not in parts and permit.adopted.get(aid) == sum(parts), 'ADOPTED_USAGE_CONFLICT')
    released = {}
    carries = {}
    for allocation in allocations:
        aid = allocation.allocation_id
        entries = (await db.scalars(select(UsageLedgerRow).where(UsageLedgerRow.allocation_id == aid))).all()
        require(entries and all(e.owner_id == owner.owner_id and e.grant_id == root.grant_id for e in entries),
                'ALLOCATION_LEDGER_IDENTITY_CONFLICT')
        require(sum(e.held_delta for e in entries) == allocation.task_held and
                sum(e.used_delta for e in entries) == sum(p.adopted.get(aid, 0) for p in permits),
                'ALLOCATION_LEDGER_BALANCE_CONFLICT')
        counter = await db.get(WindowCounterRow, allocation.window_id)
        require(counter and counter.owner_id == owner.owner_id, 'WINDOW_IDENTITY_CONFLICT')
        window_entries = (await db.scalars(select(UsageLedgerRow).join(ReservationAllocationRow,
            UsageLedgerRow.allocation_id == ReservationAllocationRow.allocation_id).where(
            ReservationAllocationRow.window_id == allocation.window_id))).all()
        require(all(e.owner_id == owner.owner_id for e in window_entries), 'WINDOW_LEDGER_IDENTITY_CONFLICT')
        used = sum(e.used_delta for e in window_entries)
        if counter.window_ref['window_type'] == 'rolling':
            cutoff = now_utc() - timedelta(seconds=counter.window_ref['duration_seconds'])
            used = sum(e.used_delta for e in window_entries if e.evidence.get('started_at') and
                       datetime.fromisoformat(e.evidence['started_at'].replace('Z', '+00:00')) > cutoff)
            # Rolling counters are refreshed lazily. Preview must remain read-only.
        else:
            if counter.used != used:
                carries[counter.window_id] = await historical_carry(db, service, counter, used)
        require(used >= 0 and counter.held == sum(e.held_delta for e in window_entries) and
                counter.held >= allocation.task_held, 'WINDOW_HELD_LEDGER_CONFLICT')
        released[aid] = allocation.task_held
    result = {'eligible': True, 'grant_id': root.grant_id, 'preview': body.preview,
              'released': released, 'overage_preserved': True, 'manifest_id': manifest.manifest_id,
              'historical_carries': carries}
    require(timedelta(0) <= now_utc() - manifest.closed_at <= timedelta(seconds=30), 'CLOSE_FACTS_STALE')
    if not body.preview:
        for allocation in allocations:
            units = released[allocation.allocation_id]
            if units:
                counter = await db.get(WindowCounterRow, allocation.window_id)
                counter.held -= units
                allocation.task_held = 0
                await service.ledger(db, owner=owner.owner_id, root=root, allocation=allocation.allocation_id,
                    key=f'reconcile-close:{body.operation_id}:{allocation.allocation_id}', kind='released', held=-units,
                    evidence={'manifest_id': manifest.manifest_id, 'operation_id': body.operation_id,
                              'evidence_ref': body.evidence_ref, 'overage_acknowledged': True,
                              'historical_carry': carries.get(allocation.window_id)})
        root.status = 'closed'
        root.settlement_status = 'settled'
    return result
