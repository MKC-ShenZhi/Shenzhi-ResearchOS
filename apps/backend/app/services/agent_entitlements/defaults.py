"""Idempotent registration initialization from the published formal Basic plan."""
import logging
from sqlalchemy import select
from app.models.agent_entitlements import OwnerEntitlementRow, EntitlementAuditRow
from .admin import admin_lock
from .assignment import assign_policy
from .lifecycle import basic_release


async def initialize_free(db, user_id=None):
    """Initialize one account; Admin initialize_only owns explicit batch backfills.

    Always take publication lock BEFORE owner lock to serialize missing-row
    creation with Admin and Billing. Never overwrite an existing assignment.
    The legacy name remains for registration callers.
    """
    if not user_id:
        return 0
    await admin_lock(db)
    owner_id = 'user:' + user_id
    owner = await db.scalar(select(OwnerEntitlementRow).where(
        OwnerEntitlementRow.owner_id == owner_id).with_for_update()
        .execution_options(populate_existing=True))
    if owner is not None:
        return 0
    revision = await basic_release(db)
    if revision is None:
        logging.getLogger('app.agent.authorization').warning(
            'Basic initialization pending: published formal Basic policy unavailable')
        return 0
    await assign_policy(db, None, owner_id, 'basic', revision, source='registration')
    from .service import now_utc, uid
    db.add(EntitlementAuditRow(audit_id=uid(), operation_id=uid(),
        principal='system:registration', reason='published_basic_initialization',
        payload={'action': 'initialize', 'owner_id': owner_id, 'before': None,
                 'after': {'plan_id': 'basic', 'policy_revision': revision, 'enabled': True,
                           'expires_at': None}}, created_at=now_utc()))
    return 1


if __name__ == '__main__':
    raise SystemExit('Use Admin migration preview and initialize_only assignment for backfills.')
