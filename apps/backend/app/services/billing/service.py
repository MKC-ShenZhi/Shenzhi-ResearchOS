"""Durable payment confirmation followed by independently retryable fulfillment."""
from datetime import timedelta
from sqlalchemy import select
from app.core.database import session_scope
from app.models.billing import BillingOrderRow
from app.models.agent_entitlements import OwnerEntitlementRow, EntitlementAuditRow, PlanReleaseRow, EntitlementPolicyRow
from app.services.agent_entitlements.admin import admin_lock
from app.services.agent_entitlements.assignment import assign_policy
from app.services.agent_entitlements.service import require, uid, now_utc, EntitlementError
from app.integrations.payment.base import provider, mode, PaymentFact
from .catalog import CATALOG


async def lock_owner(db, user_id):
    return await db.scalar(select(OwnerEntitlementRow).where(
        OwnerEntitlementRow.owner_id == 'user:' + user_id).with_for_update().execution_options(populate_existing=True))


def check_purchase(owner, plan_id):
    if not owner:
        return
    require(owner.enabled, 'ENTITLEMENT_DISABLED', 409)
    # Do not turn a permanent manual grant (including Basic) into a finite subscription.
    if owner.source != 'billing':
        require(owner.expires_at is not None and owner.expires_at <= now_utc(), 'ADMIN_ENTITLEMENT_PRESERVED')
    elif owner.expires_at and owner.expires_at > now_utc():
        require(owner.plan_id == plan_id, 'PLAN_CHANGE_NOT_SUPPORTED')


async def plans():
    async with session_scope() as db:
        items = []
        for plan in CATALOG.values():
            release = await db.get(PlanReleaseRow, plan['plan_id'])
            policy = await db.get(EntitlementPolicyRow, release.policy_revision) if release else None
            items.append({**plan, 'policy_revision': release.policy_revision if release else None,
                          'purchasable': bool(plan['purchasable'] and policy and policy.approved and not policy.test_only)})
    # Disabled installations may still display the catalog.
    try:
        payment_mode = mode()
    except EntitlementError:
        payment_mode = 'disabled'
    return {'items': items, 'payment_mode': payment_mode}


async def subscription(user_id):
    async with session_scope() as db:
        owner = await db.get(OwnerEntitlementRow, 'user:' + user_id)
        if not owner:
            return {'plan_id': None, 'status': 'unassigned', 'expires_at': None, 'source': None}
        expired = owner.expires_at is not None and owner.expires_at <= now_utc()
        return dict(plan_id=owner.plan_id, policy_revision=owner.policy_revision, source=owner.source,
                    status='disabled' if not owner.enabled else 'expired' if expired else 'active',
                    expires_at=owner.expires_at.isoformat() if owner.expires_at else None)


def view(order):
    fields = ('order_id', 'plan_id', 'policy_revision', 'amount', 'currency', 'channel', 'mode',
              'payment_status', 'fulfillment_status', 'fulfillment_error', 'transaction_id', 'payment')
    result = {name: getattr(order, name) for name in fields}
    for name in ('created_at', 'paid_at', 'fulfilled_at', 'subscription_expires_at'):
        value = getattr(order, name)
        result[name] = value.isoformat() if value else None
    return result


async def owned(db, user_id, order_id):
    order = await db.get(BillingOrderRow, order_id)
    require(order is not None and order.user_id == user_id, 'ORDER_NOT_FOUND', 404)
    return order


async def get_order(user_id, order_id):
    async with session_scope() as db:
        return view(await owned(db, user_id, order_id))


async def list_orders(user_id):
    async with session_scope() as db:
        rows = (await db.scalars(select(BillingOrderRow).where(BillingOrderRow.user_id == user_id)
                                .order_by(BillingOrderRow.created_at.desc()).limit(20))).all()
        return {'items': [view(row) for row in rows]}


async def create_order(user_id, body):
    payment_mode = mode()
    adapter = provider(body.channel)
    plan = CATALOG[body.plan_id]
    require(plan['purchasable'], 'PLAN_NOT_PURCHASABLE')
    async with session_scope() as db:
        await admin_lock(db)
        unfinished = (await db.scalars(select(BillingOrderRow).where(
            BillingOrderRow.user_id == user_id,
            (BillingOrderRow.payment_status == 'pending') |
            ((BillingOrderRow.payment_status == 'paid') & (BillingOrderRow.fulfillment_status != 'completed'))
        ).order_by(BillingOrderRow.created_at).with_for_update())).all()
        require(all(order.plan_id == body.plan_id for order in unfinished), 'UNFINISHED_ORDER_PLAN_CONFLICT')
        owner = await lock_owner(db, user_id)
        check_purchase(owner, body.plan_id)
        release = await db.get(PlanReleaseRow, body.plan_id)
        policy = await db.get(EntitlementPolicyRow, release.policy_revision) if release else None
        require(policy and policy.approved and not policy.test_only, 'PLAN_NOT_PUBLISHED')
        # Renewal pins the current subscription revision until it expires.
        revision = (owner.policy_revision if owner and owner.source == 'billing' and owner.plan_id == body.plan_id
                    and owner.expires_at and owner.expires_at > now_utc() else release.policy_revision)
        # Reuse the existing channel and snapshot; never replace a paid order.
        order = next((order for order in unfinished if order.payment_status == 'pending'), None)
        if order is None:
            order = BillingOrderRow(order_id=uid(), user_id=user_id, plan_id=body.plan_id,
                policy_revision=revision, snapshot=dict(plan), amount=plan['amount'], currency=plan['currency'],
                channel=body.channel, mode=payment_mode, merchant_id=adapter.merchant_id, app_id=adapter.app_id,
                payment_status='pending', fulfillment_status='pending', payment={}, created_at=now_utc())
            db.add(order)
            await db.flush()
        order_id = order.order_id
    # Provider failure leaves a visible order which can safely retry payment creation.
    return await prepare_payment(user_id, order_id)


async def prepare_payment(user_id, order_id):
    async with session_scope() as db:
        order = await owned(db, user_id, order_id)
        if order.payment_status != 'pending' or order.payment:
            return view(order)
    adapter = provider(order.channel, order.mode)
    require((adapter.app_id, adapter.merchant_id) == (order.app_id, order.merchant_id), 'PAYMENT_MERCHANT_CHANGED')
    payment = await adapter.create_order(order)
    async with session_scope() as db:
        order = await db.scalar(select(BillingOrderRow).where(BillingOrderRow.order_id == order_id).with_for_update())
        if order.payment_status == 'pending':
            order.payment = payment
        return view(order)


async def confirm(channel, payment_mode, fact: PaymentFact):
    # Payment commit survives any later fulfillment error.
    require(fact.status in ('paid', 'pending', 'closed'), 'PAYMENT_STATE_INVALID', 400)
    async with session_scope() as db:
        order = await db.scalar(select(BillingOrderRow).where(BillingOrderRow.order_id == fact.order_id).with_for_update())
        require(order is not None, 'ORDER_NOT_FOUND', 404)
        require((order.channel, order.mode, order.amount, order.currency, order.merchant_id, order.app_id) ==
                (channel, payment_mode, fact.amount, fact.currency, fact.merchant_id, fact.app_id), 'PAYMENT_FACT_MISMATCH', 400)
        if fact.status == 'paid':
            require(bool(fact.transaction_id), 'TRANSACTION_ID_REQUIRED', 400)
            require(order.transaction_id in (None, fact.transaction_id), 'TRANSACTION_CONFLICT', 400)
            order.payment_status = 'paid'
            order.transaction_id = fact.transaction_id
            order.paid_at = order.paid_at or now_utc()
        elif fact.status == 'closed' and order.payment_status == 'pending':
            order.payment_status = 'closed'
    if fact.status == 'paid':
        await fulfill(fact.order_id)


async def fulfill(order_id):
    async with session_scope() as db:
        await admin_lock(db)  # Same initial-assignment/publication lock as Admin.
        order = await db.scalar(select(BillingOrderRow).where(BillingOrderRow.order_id == order_id).with_for_update())
        require(order is not None, 'ORDER_NOT_FOUND', 404)
        if order.payment_status != 'paid' or order.fulfillment_status == 'completed':
            return
        try:
            async with db.begin_nested():
                if order.mode == 'mock':
                    require(mode() == 'mock', 'MOCK_PAYMENT_DISABLED', 503)
                owner = await lock_owner(db, order.user_id)
                check_purchase(owner, order.plan_id)
                now = now_utc()
                base = max(now, owner.expires_at) if owner and owner.source == 'billing' and owner.expires_at else now
                expires = base + timedelta(days=order.snapshot['duration_days'])
                owner, _ = await assign_policy(db, owner, 'user:' + order.user_id, order.plan_id,
                    order.policy_revision, expires_at=expires, source='billing')
                db.add(EntitlementAuditRow(audit_id=uid(), operation_id='billing:' + order.order_id,
                    principal='billing', reason='paid_order', created_at=now,
                    payload={'source': 'billing', 'order_id': order.order_id, 'owner_id': owner.owner_id,
                             'policy_revision': order.policy_revision, 'expires_at': expires.isoformat()}))
                order.fulfillment_status = 'completed'
                order.fulfillment_error = None
                order.fulfilled_at = now
                order.subscription_expires_at = expires
                await db.flush()
        except EntitlementError as exc:
            # Reload after savepoint rollback (SQLAlchemy expires changed attributes).
            order = await db.get(BillingOrderRow, order_id, populate_existing=True)
            order.fulfillment_error = exc.reason


async def refresh(user_id, order_id):
    async with session_scope() as db:
        order = await owned(db, user_id, order_id)
    if order.payment_status == 'pending':
        fact = await provider(order.channel, order.mode).query_order(order)
        if fact:
            require(fact.order_id == order.order_id, 'PAYMENT_ORDER_MISMATCH', 400)
            await confirm(order.channel, order.mode, fact)
    elif order.payment_status == 'paid':
        await fulfill(order_id)
    return await get_order(user_id, order_id)


async def mock_pay(user_id, order_id):
    require(mode() == 'mock', 'MOCK_PAYMENT_DISABLED', 404)
    async with session_scope() as db:
        order = await owned(db, user_id, order_id)
        require(order.mode == 'mock' and order.payment_status in ('pending', 'paid'), 'MOCK_ORDER_REQUIRED')
    adapter = provider(order.channel, order.mode)
    await confirm(order.channel, 'mock', adapter.success(order))
    return await get_order(user_id, order_id)
