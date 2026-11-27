"""Read-only shared Better Auth user and entitlement projection."""
from datetime import timedelta

from sqlalchemy import text, select, func, DateTime, cast
from pydantic import ValidationError

from app.models.agent_entitlements import (EntitlementPolicyRow, WindowCounterRow, UsageLedgerRow,
    ReservationAllocationRow, GrantRootRow, SubmissionRow)
from app.services.agent_entitlements.policy import EntitlementPolicy
from app.services.agent_entitlements.service import now_utc


JOIN = '''FROM "user" u LEFT JOIN agent_owner_entitlements e ON e.owner_id = 'user:' || u.id
    LEFT JOIN agent_entitlement_policies p ON p.policy_revision = e.policy_revision'''
# Missing, disabled, unapproved and inconsistent assignments are all visible.
ANOMALY = '''(e.owner_id IS NULL OR NOT e.enabled OR p.policy_revision IS NULL
    OR NOT p.approved OR p.test_only OR p.payload->>'plan_id' IS DISTINCT FROM e.plan_id)'''


async def list_users(db, *, page, page_size, search, plan_id):
    from app.services.agent_entitlements.admin import daily_balance
    now = now_utc()
    stats = (await db.execute(text(f'''SELECT count(*) AS total_users,
        count(*) FILTER (WHERE e.plan_id = 'free') AS free_users,
        count(*) FILTER (WHERE {ANOMALY}) AS abnormal_users {JOIN}'''))).mappings().one()
    filters = '''WHERE (:search = '' OR u.name ILIKE :pattern ESCAPE '\\' OR u.email ILIKE :pattern ESCAPE '\\')
        AND (:plan = '' OR e.plan_id = :plan OR (:plan = '__missing__' AND e.owner_id IS NULL))'''
    escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    params = {'search': search, 'pattern': f'%{escaped}%', 'plan': plan_id or '',
              'limit': page_size, 'offset': (page - 1) * page_size}
    total = await db.scalar(text(f'SELECT count(*) {JOIN} {filters}'), params)
    rows = (await db.execute(text(f'''SELECT u.id AS user_id, u.name, u.email, u."createdAt" AS created_at,
        e.plan_id, e.policy_revision, e.enabled AS entitlement_enabled, e.expires_at, e.source,
        {ANOMALY} AS abnormal {JOIN} {filters}
        ORDER BY u."createdAt" DESC, u.id LIMIT :limit OFFSET :offset'''), params)).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item['entitlement_status'] = 'pending_initialization' if item['plan_id'] is None else 'abnormal' if item.pop('abnormal') else 'ready'
        item.pop('abnormal', None)
        item['usage_windows'] = []
        item['model_calls_enabled'] = False
        expired = bool(item['plan_id'] in ('pro', 'research') and item['expires_at']
                       and item['expires_at'] <= now)
        if expired and item['entitlement_enabled']:
            active = await db.scalar(select(GrantRootRow.grant_id).join(SubmissionRow,
                SubmissionRow.submission_id == GrantRootRow.submission_id).where(
                SubmissionRow.owner_id == f"user:{item['user_id']}",
                GrantRootRow.status != 'closed').limit(1))
            item['entitlement_status'] = 'expiry_pending' if active else 'expired'
        policy_row = await db.get(EntitlementPolicyRow, item['policy_revision']) if item['policy_revision'] else None
        if policy_row:
            try:
                policy = EntitlementPolicy.model_validate(policy_row.payload)
            except ValidationError:
                item['entitlement_status'] = 'abnormal'
            else:
                item['model_calls_enabled'] = bool(policy.model_risk_profile and policy_row.approved
                                                   and not policy_row.test_only and item['entitlement_enabled']
                                                   and not expired and policy.plan_id == item['plan_id'])
                owner = f"user:{item['user_id']}"
                for rule in policy.rules:
                    window = rule.window(owner, policy.policy_revision, now)
                    counter = await db.get(WindowCounterRow, window.window_id)
                    used, held = (counter.used, counter.held) if counter else (0, 0)
                    if rule.quota_pool:
                        used, held = await daily_balance(db, owner, window)
                    if counter and window.window_type == 'rolling':
                        # Same trusted-start ledger basis as Entitlements.refresh_rolling;
                        # this read endpoint must not mutate counters or acquire write locks.
                        used = await db.scalar(select(func.coalesce(func.sum(UsageLedgerRow.used_delta), 0)).join(
                            ReservationAllocationRow, ReservationAllocationRow.allocation_id == UsageLedgerRow.allocation_id).where(
                            ReservationAllocationRow.window_id == window.window_id,
                            cast(UsageLedgerRow.evidence['started_at'].as_string(), DateTime(timezone=True)) > now - timedelta(seconds=window.duration_seconds)))
                        used = max(used, 0)
                    item['usage_windows'].append(dict(rule_id=rule.rule_id, metric=rule.metric, purpose=rule.purpose,
                        capability_id=rule.capability_id, limit=rule.limit_units, used=used, held=held,
                        remaining=max(0, rule.limit_units-used-held), window_start=window.start, window_end=window.end,
                        window_type=window.window_type, duration_seconds=window.duration_seconds,
                        accounting_basis=window.accounting_basis))
        items.append(item)
    plans = (await db.execute(text('SELECT DISTINCT plan_id FROM agent_owner_entitlements ORDER BY plan_id'))).scalars().all()
    return dict(items=items, total=total, page=page, page_size=page_size, stats=dict(stats), plans=sorted(set(plans) | {'basic', 'pro', 'research'}),
                updated_at=now, usage_status='near_realtime', usage_note='已入账实测值（Partial 为已知下界）与未释放预留分列；未结算/未知用量保留预留，不代表零消耗。')
