"""Approved Free assignment; never overwrite an operator assignment."""
import asyncio
import os

from sqlalchemy import text

from app.core.database import session_scope
from app.models.agent_entitlements import EntitlementPolicyRow, OwnerEntitlementRow
from .policy import EntitlementPolicy
from .service import require


async def initialize_free(db, user_id=None):
    if user_id is not None and await db.get(OwnerEntitlementRow, f'user:{user_id}') is not None:
        return 0
    revision = os.getenv('SHENZHI_FREE_POLICY_REVISION', '').strip()
    require(bool(revision), 'FREE_POLICY_UNCONFIGURED', 503)
    row = await db.get(EntitlementPolicyRow, revision)
    require(row is not None and row.approved and not row.test_only, 'POLICY_NOT_APPROVED', 503)
    policy = EntitlementPolicy.model_validate(row.payload)
    require(policy.plan_id == 'free' and policy.policy_revision == revision, 'FREE_POLICY_CONFLICT', 503)
    # The shared Better Auth table is authoritative. ON CONFLICT is atomic for
    # registration, first use and repeated backfills racing each other.
    result = await db.execute(text('''
        INSERT INTO agent_owner_entitlements (owner_id, policy_revision, plan_id, enabled)
        SELECT 'user:' || u.id, :revision, :plan, true FROM "user" u
        WHERE (CAST(:user_id AS text) IS NULL OR u.id = CAST(:user_id AS text))
        ON CONFLICT (owner_id) DO NOTHING
    '''), {'revision': revision, 'plan': policy.plan_id, 'user_id': user_id})
    if user_id is not None:
        require(await db.get(OwnerEntitlementRow, f'user:{user_id}') is not None, 'USER_NOT_COMMITTED', 503)
    return result.rowcount


async def main():
    async with session_scope() as db:
        count = await initialize_free(db)
    print(f'Initialized {count} missing entitlements; existing assignments preserved.')


if __name__ == '__main__':
    asyncio.run(main())
