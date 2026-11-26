"""Shared policy assignment. Caller holds publication lock and owner lock.

No commits and no identity impersonation: Admin and Billing own their audits.
"""
from sqlalchemy import select
from app.models.agent_entitlements import (EntitlementPolicyRow, OwnerEntitlementRow,
    GrantRootRow, SubmissionRow, WindowCounterRow)
from .policy import EntitlementPolicy
from .service import require, now_utc


async def assign_policy(db, owner, owner_id, plan_id, policy_revision, *, preview=False,
                        expires_at=None, source='admin'):
    row=await db.get(EntitlementPolicyRow,policy_revision)
    require(row and row.approved and not row.test_only, 'POLICY_NOT_APPROVED',403)
    policy=EntitlementPolicy.model_validate(row.payload)
    require(policy.plan_id==plan_id and policy.reservation_mode=='per_call', 'FORMAL_POLICY_CONFLICT')
    if owner and owner.policy_revision!=policy.policy_revision:
        active=await db.scalar(select(GrantRootRow.grant_id).join(SubmissionRow,
            SubmissionRow.submission_id==GrantRootRow.submission_id).where(
            SubmissionRow.owner_id==owner_id,GrantRootRow.status!='closed').limit(1))
        require(active is None, 'ACTIVE_GRANTS_REQUIRE_DRAIN')
    after={'plan_id':plan_id,'policy_revision':policy.policy_revision,'enabled':True}
    if not preview:
        if owner:
            owner.plan_id=plan_id;owner.policy_revision=policy.policy_revision;owner.enabled=True
        else:
            owner=OwnerEntitlementRow(owner_id=owner_id,**after);db.add(owner);await db.flush()
        owner.expires_at=expires_at
        owner.source=source
        rule=policy.rules[0];window=rule.window(owner_id,policy.policy_revision,now_utc())
        counter=await db.get(WindowCounterRow,window.window_id)
        if counter:counter.limit_units=rule.limit_units
    return owner, after
