import assert from "node:assert/strict";
import test from "node:test";
import { fetchEntitlementUsage } from "../../clients/backend/entitlements";
import { ApiError } from "../../clients/backend/http";

test("usage reads the public v2 wire payload with an expected identity and no caching", async () => {
  const original = globalThis.fetch;
  const payload = { schema_version: 1, plan_id: "pro", token_scope: "prompt_plus_completion", windows: [{ used_units: 123, held_units: 45, remaining_units: 832 }] };
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/api/v2/agent/entitlements");
    assert.equal(new Headers(init?.headers).get("x-shenzhi-expected-user-id"), "user-a");
    assert.equal(init?.cache, "no-store");
    assert.ok(init?.signal);
    return Response.json(payload);
  };
  try { assert.deepEqual(await fetchEntitlementUsage("user-a"), payload); }
  finally { globalThis.fetch = original; }
});

test("usage preserves unavailable entitlement errors instead of presenting zero consumption", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ error: { reason_code: "ENTITLEMENT_UNAVAILABLE", message: "ENTITLEMENT_UNAVAILABLE" } }, { status: 403 });
  try {
    await assert.rejects(fetchEntitlementUsage("user-a"), (error: unknown) => error instanceof ApiError && error.status === 403 && error.code === "ENTITLEMENT_UNAVAILABLE");
  } finally { globalThis.fetch = original; }
});
