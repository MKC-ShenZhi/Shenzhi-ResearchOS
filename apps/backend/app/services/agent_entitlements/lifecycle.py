"""Lazy expiry transitions without changing historical grants or usage.

Existing-owner callers hold only the owner lock: reading an atomic published
release does not need the global publication lock. Never acquire admin_lock
here: settlement callers may already hold an owner/grant lock.
"""
from pydantic import ValidationError
from sqlalchemy import select

from app.models.agent_entitlements import EntitlementPolicyRow, OwnerEntitlementRow, PlanReleaseRow, EntitlementAuditRow
from .policy import EntitlementPolicy


async def basic_release(db):
    release = await db.get(PlanReleaseRow, 'basic')
    row = await db.get(EntitlementPolicyRow, release.policy_revision) if release else None
    if row is None or not row.approved or row.test_only:
        return None
    try:
        policy = EntitlementPolicy.model_validate(row.payload)
    except (ValidationError, TypeError, ValueError):
        return None
    if (policy.plan_id != 'basic' or policy.reservation_mode != 'per_call'
            or policy.policy_revision != row.policy_revision):
        return None
    return row.policy_revision


async def reconcile_owner(db, owner_id):
    """Return (locked owner, pending reason); never create missing assignments.

    Callers own commit/rollback. Public subscription reads must finish their
    transaction normally even when an expired plan is awaiting grant drainage.
    """
    from .assignment import assign_policy
    from .service import EntitlementError, now_utc, uid

    owner = await db.scalar(select(OwnerEntitlementRow).where(
        OwnerEntitlementRow.owner_id == owner_id).with_for_update()
        .execution_options(populate_existing=True))
    if (owner is None or not owner.enabled or owner.plan_id not in ('pro', 'research')
            or owner.expires_at is None or now_utc() < owner.expires_at):
        return owner, None
    current = await db.get(EntitlementPolicyRow, owner.policy_revision)
    if current is None or not current.approved or current.test_only:
        return owner, 'ENTITLEMENT_POLICY_INVALID'
    try:
        policy = EntitlementPolicy.model_validate(current.payload)
    except (ValidationError, TypeError, ValueError):
        return owner, 'ENTITLEMENT_POLICY_INVALID'
    if policy.plan_id != owner.plan_id or policy.policy_revision != owner.policy_revision:
        return owner, 'ENTITLEMENT_POLICY_INVALID'
    revision = await basic_release(db)
    if revision is None:
        return owner, 'BASIC_POLICY_UNAVAILABLE'
    before = {'plan_id': owner.plan_id, 'policy_revision': owner.policy_revision,
              'enabled': owner.enabled, 'expires_at': owner.expires_at.isoformat()}
    try:
        owner, _ = await assign_policy(db, owner, owner_id, 'basic', revision,
                                       source='expiry')
    except EntitlementError as exc:
        if exc.reason == 'ACTIVE_GRANTS_REQUIRE_DRAIN':
            return owner, exc.reason
        raise
    db.add(EntitlementAuditRow(audit_id=uid(), operation_id=uid(), principal='system:expiry',
        reason='paid_plan_expired', payload={'action': 'expire', 'owner_id': owner_id,
            'before': before, 'after': {'plan_id': owner.plan_id,
                'policy_revision': owner.policy_revision, 'enabled': owner.enabled,
                'expires_at': None}}, created_at=now_utc()))
    return owner, None
