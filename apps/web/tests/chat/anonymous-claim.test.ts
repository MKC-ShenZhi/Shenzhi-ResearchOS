import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ApiError } from "../../clients/backend/http";
import {
  ANONYMOUS_CLAIM_MAX_ATTEMPTS,
  anonymousClaimAttemptUser,
  claimAnonymousSessions,
  shouldRetryAnonymousClaim,
  shouldRefreshAfterAnonymousClaim,
} from "../../features/chat/services/anonymous-claim";

test("claim client sends an empty same-origin POST and returns counts", async () => {
  let capturedInput: string | URL | Request | undefined;
  let capturedInit: RequestInit | undefined;
  const fetcher: typeof fetch = async (input, init) => {
    capturedInput = input;
    capturedInit = init;
    return new Response(JSON.stringify({
      code: 0,
      data: { moved_count: 2, skipped_streaming_count: 1, durable: true },
    }), { status: 200, headers: { "content-type": "application/json" } });
  };

  const result = await claimAnonymousSessions(fetcher);
  assert.deepEqual(result, {
    moved_count: 2,
    skipped_streaming_count: 1,
    durable: true,
  });
  assert.equal(capturedInput, "/api/chat/anonymous-claim");
  assert.equal(capturedInit?.method, "POST");
  assert.equal(capturedInit?.body, undefined);
  assert.equal(capturedInit?.headers, undefined);
});

test("claim client preserves backend failures and rejects malformed responses", async () => {
  await assert.rejects(
    claimAnonymousSessions(async () => new Response(
      JSON.stringify({ code: 10001, message: "请登录" }),
      { status: 401 },
    )),
    (error: unknown) => error instanceof ApiError && error.code === 10001 && error.status === 401,
  );
  await assert.rejects(
    claimAnonymousSessions(async () => new Response("not-json", { status: 502 })),
    /响应无法解析/,
  );
});

test("coordinator attempts once per stable user and refreshes only after durable moves", () => {
  assert.equal(anonymousClaimAttemptUser(true, "user-1", null), null);
  assert.equal(anonymousClaimAttemptUser(false, undefined, null), null);
  assert.equal(anonymousClaimAttemptUser(false, "user-1", null), "user-1");
  assert.equal(anonymousClaimAttemptUser(false, "user-1", "user-1"), null);
  assert.equal(anonymousClaimAttemptUser(false, "user-2", "user-1"), "user-2");

  assert.equal(shouldRefreshAfterAnonymousClaim({
    moved_count: 1, skipped_streaming_count: 0, durable: true,
  }), true);
  assert.equal(shouldRefreshAfterAnonymousClaim({
    moved_count: 0, skipped_streaming_count: 1, durable: true,
  }), false);
  assert.equal(shouldRefreshAfterAnonymousClaim({
    moved_count: 1, skipped_streaming_count: 0, durable: false,
  }), false);
  assert.equal(shouldRetryAnonymousClaim({
    moved_count: 0, skipped_streaming_count: 1, durable: true,
  }, 1), true);
  assert.equal(shouldRetryAnonymousClaim({
    moved_count: 0, skipped_streaming_count: 0, durable: true,
  }, 1), false);
  assert.equal(shouldRetryAnonymousClaim({
    moved_count: 0, skipped_streaming_count: 1, durable: false,
  }, 1), false);
  assert.equal(shouldRetryAnonymousClaim({
    moved_count: 0, skipped_streaming_count: 1, durable: true,
  }, ANONYMOUS_CLAIM_MAX_ATTEMPTS), false);

  const coordinator = readFileSync(
    "features/chat/components/anonymous-claim-coordinator.tsx",
    "utf8",
  );
  assert.match(coordinator, /requestReset/);
  assert.match(coordinator, /bumpHistoryRefresh/);
  assert.match(coordinator, /clearTimeout/);
  assert.match(coordinator, /shouldRetryAnonymousClaim/);
  assert.doesNotMatch(coordinator, /requestNewChat/);
});
