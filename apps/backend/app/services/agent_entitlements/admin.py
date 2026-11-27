"""Audited Admin-only plan operations. Each caller owns a database transaction."""
from datetime import datetime
from sqlalchemy import bindparam, or_, select, text
from agent_contracts.canonical import digest
from app.models.agent_entitlements import (PlanReleaseRow, EntitlementPolicyRow, OwnerEntitlementRow,
    EntitlementAuditRow, GrantRootRow, SubmissionRow, WindowCounterRow)
from .policy import EntitlementPolicy
from .plans import PLANS, POOL, build
from .service import require, uid, now_utc
from .dates import add_calendar_months


async def list_audit(db, *, page, page_size):
    rows = (await db.scalars(select(EntitlementAuditRow).where(
        or_(EntitlementAuditRow.principal.startswith('local-admin:'),
            EntitlementAuditRow.principal.startswith('ssh-admin:'))).order_by(
        EntitlementAuditRow.created_at.desc(), EntitlementAuditRow.audit_id.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    targets = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        request = payload.get('request')
        request = request if isinstance(request, dict) else {}
        ids = request.get('user_ids', [])
        ids = [value for value in ids if isinstance(value, str) and value] if isinstance(ids, list) else []
        owner = payload.get('owner_id')
        if not ids and isinstance(owner, str) and owner.startswith('user:') and owner[5:]:
            ids = [owner[5:]]
        targets.append(list(dict.fromkeys(ids)))
    user_ids = sorted({user_id for ids in targets for user_id in ids})
    emails = {}
    if user_ids:
        users = (await db.execute(text('SELECT id, email FROM "user" WHERE id IN :ids')
            .bindparams(bindparam('ids', expanding=True)), {'ids': user_ids})).mappings().all()
        emails = {user['id']: user['email'] for user in users}
    return {'items': [dict(operation_id=row.operation_id, principal=row.principal, reason=row.reason,
        created_at=row.created_at.isoformat(), payload=row.payload,
        target_accounts=[{'user_id': user_id, 'email': emails.get(user_id)} for user_id in ids])
        for row, ids in zip(rows, targets)], 'page': page}


async def admin_lock(db):
    # Serializes publication, initial assignment and operation-id replay on PostgreSQL.
    # Quota/settlement operations still use the owner -> grant lock order.
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(739201120)'))


async def replay(db, operation_id, principal, request):
    old = await db.scalar(select(EntitlementAuditRow).where(EntitlementAuditRow.operation_id == operation_id))
    if old:
        require(old.principal == principal and old.payload.get('request') == request, 'IDEMPOTENCY_CONFLICT')
        return old.payload['result']


async def daily_balance(db, owner_id, window):
    """One daily Token bucket across revisions; legacy daily-tokens debt remains.

    Add balances for the SAME daily accounting rule, never add independent limits.
    All callers mutating quota already hold the owner lock.
    """
    rows = (await db.scalars(select(WindowCounterRow).where(
        WindowCounterRow.owner_id == owner_id, WindowCounterRow.rule_id == 'daily-tokens'))).all()
    used = held = 0
    for row in rows:
        ref = row.window_ref
        if (ref.get('window_type') == 'natural' and ref.get('timezone') == 'Asia/Shanghai'
                and ref.get('start') and datetime.fromisoformat(ref['start'].replace('Z','+00:00')) == window.start):
            used += row.used
            held += row.held
    return used, held


async def plans_view(db):
    items = []
    for plan_id, (name, limit) in PLANS.items():
        release = await db.get(PlanReleaseRow, plan_id)
        row = await db.get(EntitlementPolicyRow, release.policy_revision) if release else None
        policy = EntitlementPolicy.model_validate(row.payload) if row else None
        items.append(dict(plan_id=plan_id, name=name, daily_tokens=limit, price=0,
            deep_research=plan_id=='research', policy_revision=release.policy_revision if release else None,
            published=bool(row and row.approved and not row.test_only),
            model_risk_ready=bool(policy and policy.model_risk_profile and (not policy.dynamic_model_budget or policy.model_budget_profiles)),
            capabilities=[c.capability_id for c in policy.permission_snapshot.capabilities] if policy else [],
            published_at=release.published_at.isoformat() if release else None))
    return {'items':items}


async def publish(db, body, principal, runtime):
    await admin_lock(db)
    request = body.model_dump(mode='json')
    old = await replay(db, body.operation_id, principal, request)
    if old is not None:
        return old
    require(body.approval_ref, 'POLICY_APPROVAL_REQUIRED', 422)
    supplied = {p.plan_id:p for p in body.policies}
    require(set(supplied)==set(PLANS), 'FORMAL_PLANS_REQUIRED', 422)
    first=supplied['basic']
    require(first.policy_revision.startswith('basic-v1-'), 'POLICY_REVISION_INVALID', 422)
    try:
        expected=build(body.capabilities, release=first.policy_revision[len('basic-v1-'):],
                       model_budgets={k:v.model_dump(mode='json') for k,v in first.model_budget_profiles.items()},
                       risk_profile=first.model_risk_profile)
    except (ValueError, KeyError, TypeError):
        require(False, 'CAPABILITY_EXPORT_INVALID',422)
    expected={p['plan_id']:p for p in expected['policies']}
    require(all(p.model_dump(mode='json')==expected[k] for k,p in supplied.items()), 'FORMAL_POLICY_CONFLICT', 422)
    require(not first.model_risk_profile or body.risk_approval_ref, 'MODEL_RISK_APPROVAL_REQUIRED', 422)
    # Online public config proves model/skill names currently exposed; tool build
    # identities are approved from the controlled offline export, never fabricated.
    model_ids={'model:'+m['value'] for m in runtime['models'] if m['enabled']}
    skill_ids={'skill:'+s['name'] for s in runtime['skills']}
    real_ids={e['identity']['capability_id'] for e in body.capabilities['capabilities']}
    require(model_ids == {i for i in real_ids if i.startswith('model:')} and
            skill_ids == {i for i in real_ids if i.startswith('skill:')}, 'RUNTIME_CATALOG_CHANGED', 409)
    for plan_id, policy in supplied.items():
        require(await db.get(EntitlementPolicyRow,policy.policy_revision) is None, 'POLICY_REVISION_IMMUTABLE')
        db.add(EntitlementPolicyRow(policy_revision=policy.policy_revision, approved=True, test_only=False,
                                   payload=policy.model_dump(mode='json')))
        await db.flush()
        release=await db.get(PlanReleaseRow,plan_id)
        if release:
            release.policy_revision=policy.policy_revision; release.published_at=now_utc()
        else:
            db.add(PlanReleaseRow(plan_id=plan_id,policy_revision=policy.policy_revision,published_at=now_utc()))
    result={'revisions':{k:p.policy_revision for k,p in supplied.items()}}
    db.add(EntitlementAuditRow(audit_id=uid(),operation_id=body.operation_id,principal=principal,
        reason=body.reason,payload={'action':'publish','request':request,'result':result},created_at=now_utc()))
    return result


async def change_one(db, body, user_id, principal):
    require(bool(user_id) and len(user_id)<=250, 'USER_ID_INVALID',422)
    exists=await db.scalar(text('SELECT id FROM "user" WHERE id = :id'),{'id':user_id})
    require(exists is not None, 'USER_NOT_FOUND',404)
    owner_id='user:'+user_id
    owner=await db.scalar(select(OwnerEntitlementRow).where(OwnerEntitlementRow.owner_id==owner_id)
                          .with_for_update().execution_options(populate_existing=True))
    before={'plan_id':owner.plan_id if owner else None,'policy_revision':owner.policy_revision if owner else None,
            'enabled':owner.enabled if owner else None,
            'expires_at':owner.expires_at.isoformat() if owner and owner.expires_at else None,
            'source':owner.source if owner else None}
    if body.initialize_only:
        require(owner is None and body.action=='assign' and body.plan_id=='basic', 'EXISTING_ASSIGNMENT_PRESERVED')
    if body.action=='assign':
        require(body.plan_id and body.policy_revision, 'PLAN_REVISION_REQUIRED',422)
        release=await db.get(PlanReleaseRow,body.plan_id)
        require(release is not None and release.policy_revision==body.policy_revision, 'PLAN_RELEASE_CHANGED')
        from .assignment import assign_policy
        expires_at = add_calendar_months(now_utc(), body.duration_months) if body.duration_months else None
        owner, after = await assign_policy(db, owner, owner_id, body.plan_id, body.policy_revision,
                                          preview=body.preview, expires_at=expires_at, source='admin')
        after={**after, 'expires_at':expires_at.isoformat() if expires_at else None, 'source':'admin'}
    else:
        require(owner is not None, 'ENTITLEMENT_UNASSIGNED',403)
        require(body.action!='restore' or owner.plan_id in PLANS, 'FORMAL_PLAN_REQUIRED',403)
        if body.action == 'restore':
            row = await db.get(EntitlementPolicyRow, owner.policy_revision)
            require(row and row.approved and not row.test_only, 'POLICY_NOT_APPROVED',403)
        after={**before,'enabled':body.action=='restore','source':'admin'}
        if not body.preview:
            owner.enabled=after['enabled']
            owner.source='admin'
    return {'user_id':user_id,'status':'preview' if body.preview else 'success','before':before,'after':after}


async def assign(db, body, principal):
    from .service import EntitlementError
    await admin_lock(db)
    request=body.model_dump(mode='json')
    old=await replay(db,body.operation_id,principal,request)
    if old is not None:return old
    require(len(body.user_ids)==len(set(body.user_ids)), 'DUPLICATE_USER_IDS',422)
    results=[]
    # Stable lock order for overlapping batches. Per-user savepoints allow honest partial success.
    for user_id in sorted(body.user_ids):
        try:
            async with db.begin_nested():
                result=await change_one(db,body,user_id,principal)
                await db.flush()
            results.append(result)
        except EntitlementError as exc:
            results.append({'user_id':user_id,'status':'failed','reason':exc.reason})
    result={'items':results,'preview':body.preview}
    if not body.preview:
        db.add(EntitlementAuditRow(audit_id=uid(),operation_id=body.operation_id,principal=principal,
            reason=body.reason,payload={'action':body.action,'approval_ref':body.approval_ref,'request':request,'result':result},created_at=now_utc()))
    return result


async def migration_preview(db, before, limit):
    require(before.tzinfo is not None,'TIMEZONE_REQUIRED',422)
    rows=(await db.execute(text('''SELECT u.id, u.email, u."createdAt" FROM "user" u
        LEFT JOIN agent_owner_entitlements e ON e.owner_id = 'user:' || u.id
        WHERE e.owner_id IS NULL AND u."createdAt" < :before ORDER BY u."createdAt",u.id LIMIT :limit'''),
        {'before':before,'limit':limit})).mappings().all()
    return {'items':[dict(r) for r in rows], 'before':before.isoformat(), 'initialize_only':True}
