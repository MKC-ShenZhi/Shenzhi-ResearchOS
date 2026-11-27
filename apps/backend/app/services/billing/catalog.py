"""Alipay sandbox demo prices in CNY fen, independent of Agent policy definitions."""
from app.services.agent_entitlements.plans import PLANS

CATALOG = {
    plan_id: dict(plan_id=plan_id, name=name, daily_tokens=tokens, amount=amount,
                  currency='CNY', duration_months=1, purchasable=plan_id != 'basic', test_price=True)
    for (plan_id, (name, tokens)), amount in zip(PLANS.items(), (0, 1990, 4990))
}
