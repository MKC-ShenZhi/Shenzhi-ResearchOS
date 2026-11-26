"""Batch stored health evidence, bound to current Agent capability identities."""
from datetime import timedelta
from sqlalchemy import select, tuple_
from app.models.agent_management import ManagementAuditRow
from app.integrations import agent_management as agent
from . import agent_management_audit as audit
from pydantic import RootModel
from agent_contracts.canonical import digest


async def summary(request):
    identities = await agent.request('POST', '/identities', RootModel[dict],
                                     payload=request.model_dump(mode='json'))
    pairs = [(item.kind, item.target_id) for item in request.targets]
    fingerprints = {(kind, digest(target)): target for kind, target in pairs}
    async with audit.get_session_factory()() as db:
        rows = (await db.scalars(select(ManagementAuditRow).where(
            ManagementAuditRow.action == 'check',
            tuple_(ManagementAuditRow.target_kind, ManagementAuditRow.target_fingerprint).in_(fingerprints),
            ManagementAuditRow.created_at >= audit.now() - timedelta(days=1))
            .order_by(ManagementAuditRow.created_at.desc()).limit(5001))).all()
    latest = {}
    for row in rows[:5000]:
        key = (row.target_kind, fingerprints[(row.target_kind, row.target_fingerprint)])
        if key not in latest:
            latest[key] = audit.entry(row)
    items = []
    for kind, target in pairs:
        entry = latest.get((kind, target))
        check = entry.check if entry else None
        identity = identities.root.get(kind + '/' + target)
        state, reason = 'unknown', 'NO_CURRENT_CHECK'
        if check:
            state, reason = check.state, check.reason
            if not identity or not check.capability_version or check.capability_version != identity:
                state, reason = 'stale', 'CAPABILITY_VERSION_CHANGED_OR_UNKNOWN'
            elif check.expires_at <= audit.now():
                state, reason = 'stale', 'CHECK_EXPIRED'
        elif entry:
            state, reason = entry.state, entry.reason
        items.append(dict(kind=kind, target_id=target, state=state, reason=reason,
                          check=check.model_dump(mode='json') if check else None,
                          audit_id=str(entry.audit_id) if entry else None))
    return {'items': items, 'observed_at': audit.now().isoformat(), 'truncated': len(rows) > 5000}
