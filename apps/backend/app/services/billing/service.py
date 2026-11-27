"""Durable payment confirmation followed by independently retryable fulfillment."""
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json
from sqlalchemy import select
from app.core.database import session_scope
from app.models.billing import BillingOrderRow
from app.models.agent_entitlements import OwnerEntitlementRow, EntitlementAuditRow, PlanReleaseRow, EntitlementPolicyRow
from app.services.agent_entitlements.admin import admin_lock
from app.services.agent_entitlements.assignment import assign_policy
from app.services.agent_entitlements.service import require, uid, now_utc, EntitlementError
from app.integrations.payment.base import provider, mode, PaymentFact
from .catalog import CATALOG
from app.services.agent_entitlements.dates import add_calendar_months
from app.services.agent_entitlements.lifecycle import reconcile_owner


async def lock_owner(db, user_id):
    return await db.scalar(select(OwnerEntitlementRow).where(
        OwnerEntitlementRow.owner_id == 'user:' + user_id).with_for_update().execution_options(populate_existing=True))


def owner_snapshot(owner):
    if owner is None:
        return None
    return dict(plan_id=owner.plan_id, policy_revision=owner.policy_revision,
                enabled=owner.enabled, source=owner.source,
                expires_at=owner.expires_at.isoformat() if owner.expires_at else None)


def check_purchase(owner, plan_id, at=None):
    at = at or now_utc()
    if not owner:
        return 'purchase'
    require(owner.enabled, 'ENTITLEMENT_DISABLED', 409)
    if owner.plan_id in ('pro', 'research'):
        require(owner.expires_at is not None, 'LEGACY_PERMANENT_ENTITLEMENT_REQUIRES_ADMIN')
        if owner.expires_at > at:
            if owner.plan_id == 'pro' and plan_id == 'research':
                return 'upgrade'
            require(owner.plan_id == plan_id, 'PLAN_CHANGE_NOT_SUPPORTED')
            return 'renew'
    return 'purchase'


def upgrade_quote(user_id, owner, revision, at):
    """Value remaining natural months, anchored backwards from the retained expiry.

    Recalculation at the submitted timestamp validates every value: the client
    supplies no price, owner, policy or expiry. No stored quote/session is needed.
    """
    require(at.tzinfo is not None and at.utcoffset() is not None, 'QUOTE_INVALID')
    require(check_purchase(owner, 'research', at) == 'upgrade', 'UPGRADE_NOT_AVAILABLE')
    end = owner.expires_at
    remaining = Fraction(0)
    months = 1
    while end > at:
        start = add_calendar_months(owner.expires_at, -months)
        remaining += Fraction((end - max(start, at)) // timedelta(microseconds=1),
                              (end - start) // timedelta(microseconds=1))
        end = start
        months += 1
    value = (CATALOG['research']['amount'] - CATALOG['pro']['amount']) * remaining
    # Round once, half-up to integer fen; a positive remaining term costs >= 1 fen.
    amount = max(1, (2 * value.numerator + value.denominator) // (2 * value.denominator))
    result = dict(action='upgrade', plan_id='research', policy_revision=revision,
                  owner_snapshot=owner_snapshot(owner), amount=amount, currency=CATALOG['research']['currency'],
                  quoted_at=at.isoformat(), quote_expires_at=min(at + timedelta(minutes=5), owner.expires_at).isoformat(),
                  subscription_expires_at=owner.expires_at.isoformat())
    result['quote_token'] = sha256(json.dumps({'user_id': user_id, **result}, sort_keys=True).encode()).hexdigest()
    return result


async def quote(user_id, plan_id):
    require(plan_id == 'research', 'UPGRADE_NOT_AVAILABLE')
    async with session_scope() as db:
        await admin_lock(db)
        owner, pending = await reconcile_owner(db, 'user:' + user_id)
        require(pending is None, pending or 'ENTITLEMENT_CHANGED')
        release = await db.get(PlanReleaseRow, plan_id)
        require(release is not None, 'PLAN_NOT_PUBLISHED')
        await assign_policy(db, owner, 'user:' + user_id, plan_id, release.policy_revision, preview=True)
        return upgrade_quote(user_id, owner, release.policy_revision, now_utc())


def check_upgrade_snapshot(order, owner, at, *, payment=False):
    snapshot = order.snapshot
    require(snapshot.get('owner_snapshot') is not None and
            snapshot.get('subscription_expires_at') and snapshot.get('quote_expires_at') and
            snapshot.get('quote_token'), 'QUOTE_SNAPSHOT_INVALID')
    require(owner_snapshot(owner) == snapshot['owner_snapshot'], 'ENTITLEMENT_CHANGED')
    require(check_purchase(owner, order.plan_id, at) == 'upgrade', 'UPGRADE_NOT_AVAILABLE')
    require(snapshot['subscription_expires_at'] == owner.expires_at.isoformat(), 'QUOTE_SNAPSHOT_INVALID')
    if payment:
        require(at < datetime.fromisoformat(snapshot['quote_expires_at']), 'QUOTE_EXPIRED')
    return datetime.fromisoformat(snapshot['subscription_expires_at'])


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
        owner, pending = await reconcile_owner(db, 'user:' + user_id)
        if not owner:
            return {'plan_id': None, 'status': 'unassigned', 'expires_at': None, 'source': None}
        expired = owner.expires_at is not None and owner.expires_at <= now_utc()
        return dict(plan_id=owner.plan_id, policy_revision=owner.policy_revision, source=owner.source,
                    status='disabled' if not owner.enabled else 'expired' if expired else 'active',
                    expires_at=owner.expires_at.isoformat() if owner.expires_at else None,
                    transition_pending_reason=pending)


def view(order):
    fields = ('order_id', 'plan_id', 'policy_revision', 'amount', 'currency', 'channel', 'mode',
              'payment_status', 'fulfillment_status', 'fulfillment_error', 'transaction_id', 'payment')
    result = {name: getattr(order, name) for name in fields}
    result['action'] = order.snapshot.get('action', 'purchase')
    result['quote_expires_at'] = order.snapshot.get('quote_expires_at') if result['action'] == 'upgrade' else None
    for name in ('created_at', 'paid_at', 'fulfilled_at', 'subscription_expires_at'):
        value = getattr(order, name)
        result[name] = value.isoformat() if value else None
    if result['action'] == 'upgrade' and result['subscription_expires_at'] is None:
        result['subscription_expires_at'] = order.snapshot.get('subscription_expires_at')
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
        now = now_utc()
        unfinished = (await db.scalars(select(BillingOrderRow).where(
            BillingOrderRow.user_id == user_id,
            (BillingOrderRow.payment_status == 'pending') |
            ((BillingOrderRow.payment_status == 'paid') & (BillingOrderRow.fulfillment_status != 'completed'))
        ).order_by(BillingOrderRow.created_at).with_for_update())).all()
        # Retain expired upgrade orders and all payment facts. A delayed verified
        # payment can still be recorded; fulfillment must pass the owner snapshot.
        for previous in unfinished:
            if (previous.payment_status == 'pending' and previous.snapshot.get('action') == 'upgrade'
                    and previous.snapshot.get('quote_expires_at')
                    and datetime.fromisoformat(previous.snapshot['quote_expires_at']) <= now):
                previous.payment_status = 'closed'
        unfinished = [order for order in unfinished if order.payment_status != 'closed']
        require(all(order.plan_id == body.plan_id for order in unfinished), 'UNFINISHED_ORDER_PLAN_CONFLICT')
        require(not any(order.payment_status == 'paid' for order in unfinished), 'PAID_ORDER_REQUIRES_FULFILLMENT')
        owner, pending = await reconcile_owner(db, 'user:' + user_id)
        require(pending is None, pending or 'ENTITLEMENT_CHANGED')
        action = check_purchase(owner, body.plan_id)
        # An expired/changed upgrade must never silently become a full-price
        # purchase or renewal after the user confirmed a discounted quote.
        if body.expected_quote is not None:
            require(action == 'upgrade', 'UPGRADE_NOT_AVAILABLE')
        release = await db.get(PlanReleaseRow, body.plan_id)
        policy = await db.get(EntitlementPolicyRow, release.policy_revision) if release else None
        require(policy and policy.approved and not policy.test_only, 'PLAN_NOT_PUBLISHED')
        revision = owner.policy_revision if action == 'renew' else release.policy_revision
        await assign_policy(db, owner, 'user:' + user_id, body.plan_id, revision, preview=True)
        order = next((order for order in unfinished if order.payment_status == 'pending'), None)
        if order is not None:
            require((order.snapshot.get('action') == 'upgrade') == (action == 'upgrade'), 'ENTITLEMENT_CHANGED')
            if action == 'upgrade':
                check_upgrade_snapshot(order, owner, now, payment=True)
                if body.expected_quote is not None:
                    require(body.expected_quote.quote_token == order.snapshot['quote_token'], 'QUOTE_CHANGED')
            if 'owner_snapshot' in order.snapshot:
                require(order.snapshot['owner_snapshot'] == owner_snapshot(owner), 'ENTITLEMENT_CHANGED')
        if order is None:
            snapshot = {**plan, 'action': action, 'owner_snapshot': owner_snapshot(owner)}
            if action == 'upgrade':
                expected = body.expected_quote
                require(expected is not None, 'QUOTE_REQUIRED')
                require(expected.quoted_at.tzinfo is not None and expected.quoted_at <= now, 'QUOTE_INVALID')
                require(now < expected.quoted_at + timedelta(minutes=5), 'QUOTE_EXPIRED')
                quoted = upgrade_quote(user_id, owner, revision, expected.quoted_at)
                require(quoted['quote_token'] == expected.quote_token, 'QUOTE_CHANGED')
                snapshot.update(quoted)
            order = BillingOrderRow(order_id=uid(), user_id=user_id, plan_id=body.plan_id,
                policy_revision=revision, snapshot=snapshot,
                amount=snapshot['amount'], currency=plan['currency'],
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
        if order.payment_status != 'pending':
            return view(order)
        if order.snapshot.get('action') == 'upgrade':
            owner = await lock_owner(db, user_id)
            check_upgrade_snapshot(order, owner, now_utc(), payment=True)
        if 'owner_snapshot' in order.snapshot:
            owner = await lock_owner(db, user_id)
            require(owner_snapshot(owner) == order.snapshot['owner_snapshot'], 'ENTITLEMENT_CHANGED')
        if order.payment:
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
                now = now_utc()
                if 'owner_snapshot' in order.snapshot:
                    require(owner_snapshot(owner) == order.snapshot['owner_snapshot'], 'ENTITLEMENT_CHANGED')
                if order.snapshot.get('action') == 'upgrade':
                    # Quote TTL gates checkout, never delayed callbacks/retries.
                    expires = check_upgrade_snapshot(order, owner, now)
                else:
                    require(check_purchase(owner, order.plan_id) != 'upgrade', 'ENTITLEMENT_CHANGED')
                    base = max(now, owner.expires_at) if owner and owner.expires_at else now
                    if 'duration_months' in order.snapshot:
                        expires = add_calendar_months(base, order.snapshot['duration_months'])
                    else:
                        # Historical paid orders retain their original fixed-day contract.
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
