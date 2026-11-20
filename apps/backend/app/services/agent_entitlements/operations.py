"""Audited operator operations; never exposed to browser or Worker credentials."""
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.models.agent_entitlements import (
    EntitlementAuditRow, ReservationAllocationRow, UsageLedgerRow, WindowCounterRow,
)
from .service import now_utc, require, uid


async def adjust_usage(db, service, *, operation_id, principal, allocation_id, used_delta,
                       reason, evidence_ref, effective_started_at):
    require(principal and reason and evidence_ref and type(used_delta) is int, 'ADJUSTMENT_AUDIT_REQUIRED', 422)
    require(effective_started_at.tzinfo is not None, 'ADJUSTMENT_TIMEZONE_REQUIRED', 422)
    allocation = await db.get(ReservationAllocationRow, allocation_id)
    require(allocation is not None, 'ALLOCATION_NOT_FOUND', 404)
    owner, root, _ = await service.lock_grant(db, allocation.grant_id)
    payload = dict(allocation_id=allocation_id, used_delta=used_delta, reason=reason,
                   evidence_ref=evidence_ref, started_at=effective_started_at.isoformat())
    old = await db.scalar(select(EntitlementAuditRow).where(EntitlementAuditRow.operation_id == operation_id))
    if old:
        require(old.payload == payload and old.principal == principal, 'ADJUSTMENT_CONFLICT')
        return old.audit_id
    counter = await db.get(WindowCounterRow, allocation.window_id)
    await service.refresh_rolling(db, counter, now_utc())
    current_used = await db.scalar(select(func.coalesce(func.sum(UsageLedgerRow.used_delta), 0)).where(
        UsageLedgerRow.allocation_id == allocation_id))
    require(current_used + used_delta >= 0, 'ADJUSTMENT_NEGATIVE_BALANCE')
    window = allocation.allocation['window_ref']
    applies_now = True
    if window['window_type'] == 'rolling':
        applies_now = effective_started_at > now_utc() - timedelta(seconds=window['duration_seconds'])
    else:
        require(datetime.fromisoformat(window['start'].replace('Z','+00:00')) <= effective_started_at <
                datetime.fromisoformat(window['end'].replace('Z','+00:00')), 'ADJUSTMENT_WINDOW_CONFLICT')
    if applies_now:
        require(counter.used + used_delta >= 0, 'ADJUSTMENT_NEGATIVE_BALANCE')
        counter.used += used_delta
    root.overage = root.overage or counter.used + counter.held > counter.limit_units
    root.settlement_status = 'reconciliation_required'
    await service.ledger(db, owner=owner.owner_id, root=root, allocation=allocation_id,
        key='manual:' + operation_id, kind='adjustment', used=used_delta, evidence=payload)
    audit = EntitlementAuditRow(audit_id=uid(), operation_id=operation_id, principal=principal,
                               reason=reason, payload=payload, created_at=now_utc())
    db.add(audit)
    return audit.audit_id
