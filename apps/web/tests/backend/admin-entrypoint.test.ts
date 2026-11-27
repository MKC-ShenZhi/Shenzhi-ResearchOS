import assert from "node:assert/strict";
import test from "node:test";
import type { NextRequest } from "next/server";
import { forwardToBusinessBackend } from "../../clients/backend/forward";

test("public BFF blocks Admin before identity resolution or upstream requests", async () => {
  // An unusable request/origin proves blocked paths never reach forwarding.
  for (const path of [
    ["admin-console"], ["admin-console", "auth", "login"],
    ["%61dmin-console", "users"], ["admin-console%2Fusers"],
    ["knowledge", "..", "admin-console", "users"], ["%invalid"],
  ]) {
    const response = await forwardToBusinessBackend({} as NextRequest, "invalid-origin", path);
    assert.equal(response.status, 404);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  }
});
