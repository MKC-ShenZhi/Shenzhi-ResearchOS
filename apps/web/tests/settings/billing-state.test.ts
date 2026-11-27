import assert from "node:assert/strict";
import test from "node:test";
import { purchaseBlock } from "../../features/settings/components/subscription/billing-state";
import type { BillingPlan, Subscription } from "../../clients/backend/billing";

const plan = (plan_id: string): BillingPlan => ({ plan_id, name: plan_id, amount: plan_id === "research" ? 4990 : 1990,
  currency: "CNY", daily_tokens: 1000000, duration_months: 1, purchasable: true, test_price: true });
const subscription = (plan_id: string, source: string): Subscription => ({ plan_id, source,
  status: "active", expires_at: plan_id === "basic" ? null : "2028-01-31T00:00:00Z" });

test("Basic can purchase either paid plan regardless of assignment source", () => {
  for (const source of ["registration", "expiry", "admin", "billing"]) {
    for (const target of ["pro", "research"]) assert.equal(purchaseBlock(subscription("basic", source), plan(target)), null);
  }
});

test("finite administrator gifts allow renewal and Pro upgrade, but no Research downgrade", () => {
  for (const current of ["pro", "research"]) {
    assert.equal(purchaseBlock(subscription(current, "admin"), plan(current)), null);
    assert.equal(purchaseBlock(subscription(current, "admin"), plan(current === "pro" ? "research" : "pro")), current === "pro" ? null : "PLAN_CHANGE_NOT_SUPPORTED");
  }
});

test("free Basic, disabled, permanent and draining entitlements remain protected", () => {
  assert.equal(purchaseBlock(subscription("basic", "registration"), plan("basic")), "BASIC_FREE_FOREVER");
  assert.equal(purchaseBlock({ ...subscription("pro", "admin"), status: "disabled" }, plan("pro")), "ENTITLEMENT_DISABLED");
  assert.equal(purchaseBlock({ ...subscription("pro", "admin"), expires_at: null }, plan("pro")), "LEGACY_PERMANENT_ENTITLEMENT_REQUIRES_ADMIN");
  assert.equal(purchaseBlock({ ...subscription("pro", "billing"), status: "expired", transition_pending_reason: "ACTIVE_GRANTS_REQUIRE_DRAIN" }, plan("pro")), "ACTIVE_GRANTS_REQUIRE_DRAIN");
});

test("unassigned users may purchase; unpublished plans stay unavailable", () => {
  const missing: Subscription = { plan_id: null, status: "unassigned", source: null, expires_at: null };
  assert.equal(purchaseBlock(missing, plan("pro")), null);
  assert.equal(purchaseBlock(missing, { ...plan("pro"), purchasable: false }), "PLAN_NOT_PUBLISHED");
});
