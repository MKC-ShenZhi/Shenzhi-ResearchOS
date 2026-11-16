import assert from "node:assert/strict";
import test from "node:test";

import { deleteCurrentAccount } from "../../features/settings/services/account-deletion";
import {
  sendSetPasswordOtp,
  setPasswordWithOtp,
} from "../../features/settings/services/account-password";

async function withFetch(
  implementation: typeof fetch,
  run: () => Promise<void>,
) {
  const original = globalThis.fetch;
  globalThis.fetch = implementation;
  try {
    await run();
  } finally {
    globalThis.fetch = original;
  }
}

test("initial-password services convert network failures into stable results", async () => {
  await withFetch(
    async () => { throw new TypeError("offline"); },
    async () => {
      assert.deepEqual(await sendSetPasswordOtp(), {
        ok: false,
        message: "send_otp_failed",
      });
      assert.deepEqual(await setPasswordWithOtp("123456", "Password12345"), {
        ok: false,
        message: "set_password_failed",
      });
    },
  );
});

test("account deletion preserves server request IDs and safely handles network failure", async () => {
  await withFetch(
    async () => new Response(JSON.stringify({ message: "cleanup unavailable" }), {
      status: 503,
      headers: { "X-Request-Id": "delete-request-123" },
    }),
    async () => {
      assert.deepEqual(await deleteCurrentAccount(), {
        ok: false,
        message: "cleanup unavailable",
        status: 503,
        requestId: "delete-request-123",
      });
    },
  );

  await withFetch(
    async () => { throw new TypeError("offline"); },
    async () => {
      assert.deepEqual(await deleteCurrentAccount(), {
        ok: false,
        message: "账号注销服务暂不可用，请稍后重试",
      });
    },
  );
});
