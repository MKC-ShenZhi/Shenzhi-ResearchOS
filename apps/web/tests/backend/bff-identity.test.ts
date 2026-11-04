import assert from "node:assert/strict";
import test from "node:test";

import { attachIdentity, attachMigrationIdentity, resolveBackendIdentity } from "../../clients/backend/identity";

test("BFF distinguishes an anonymous session from a Better Auth failure", async () => {
  assert.deepEqual(await resolveBackendIdentity(new Headers(), async () => null), { kind: "anonymous" });

  await assert.rejects(
    resolveBackendIdentity(new Headers(), async () => { throw new Error("database unavailable"); }),
    /database unavailable/,
  );
});

test("BFF attaches exactly one identity returned by Better Auth", async () => {
  const identity = await resolveBackendIdentity(new Headers(), async () => ({
    user: { id: "user-1", email: "user@example.com" },
  }));
  const outgoing = new Headers({
    "x-shenzhi-anonymous-id": "00000000-0000-4000-8000-000000000001",
    "x-shenzhi-user-email": "forged@example.com",
  });
  attachIdentity(outgoing, identity, "00000000-0000-4000-8000-000000000001");
  assert.equal(outgoing.get("x-shenzhi-user-id"), "user-1");
  assert.equal(outgoing.has("x-shenzhi-anonymous-id"), false);
  assert.equal(outgoing.has("x-shenzhi-user-email"), false);

  const anonymous = await resolveBackendIdentity(new Headers(), async () => null);
  attachIdentity(outgoing, anonymous, "00000000-0000-4000-8000-000000000001");
  assert.equal(outgoing.has("x-shenzhi-user-id"), false);
  assert.equal(outgoing.get("x-shenzhi-anonymous-id"), "00000000-0000-4000-8000-000000000001");
});

test("BFF attaches source and target identity only for anonymous claim", () => {
  const outgoing = new Headers({
    "x-shenzhi-user-id": "forged-user",
    "x-shenzhi-user-email": "forged@example.com",
    "x-shenzhi-anonymous-id": "00000000-0000-4000-8000-000000000099",
    "x-shenzhi-source-anonymous-id": "00000000-0000-4000-8000-000000000098",
  });
  attachMigrationIdentity(outgoing, "user-1", "00000000-0000-4000-8000-000000000001");
  assert.equal(outgoing.get("x-shenzhi-user-id"), "user-1");
  assert.equal(outgoing.get("x-shenzhi-source-anonymous-id"), "00000000-0000-4000-8000-000000000001");
  assert.equal(outgoing.has("x-shenzhi-user-email"), false);
  assert.equal(outgoing.has("x-shenzhi-anonymous-id"), false);
});
