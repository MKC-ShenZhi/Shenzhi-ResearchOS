import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";
import { ApiError } from "../../clients/backend/http";
import { restoreTurns } from "../../features/chat/services/conversation";

const bubble = readFileSync(
  resolve(process.cwd(), "features/chat/components/error-bubble.tsx"),
  "utf8",
);
const thread = readFileSync(
  resolve(process.cwd(), "features/chat/components/chat-thread.tsx"),
  "utf8",
);
const paperAssistant = readFileSync(
  resolve(process.cwd(), "features/papers/[id]/components/paper-assistant-panel.tsx"),
  "utf8",
);

test("failed Chat turns show requestId on the error bubble without changing the envelope contract", () => {
  assert.match(bubble, /requestId\?: string/);
  assert.match(bubble, /请求 ID：/);
  assert.match(bubble, /navigator\.clipboard\.writeText\(requestId\)/);
  assert.match(bubble, /复制 ID/);
  assert.doesNotMatch(bubble, /\{code,\s*message\}/);
  assert.match(thread, /requestId=\{turn\.requestId\}/);
  assert.match(paperAssistant, /requestId=\{turn\.requestId\}/);
});

test("API errors keep requestId on the client error object, not in the business envelope", () => {
  const withId = new ApiError(20009, "仅支持继续最近一条已停止或失败的回答", 409, {
    requestId: "req-live-1",
  });
  assert.equal(withId.requestId, "req-live-1");
  assert.equal(withId.message, "仅支持继续最近一条已停止或失败的回答");
  assert.equal(withId.code, 20009);
  const errors = readFileSync(
    resolve(process.cwd(), "features/chat/services/errors.ts"),
    "utf8",
  );
  assert.match(errors, /export function requestIdForApiError/);
  assert.match(errors, /error instanceof ApiError \? error\.requestId/);
});

test("history restore keeps the server error text and does not invent a requestId", () => {
  const turns = restoreTurns({
    id: "s",
    title: "q",
    favorite: false,
    updated_at: 0,
    mode: "deep",
    model: "m",
    web_search: true,
    messages: [{
      id: "m",
      question: "q",
      content: "",
      reasoning: "",
      status: "failed",
      references: [],
      followups: [],
      duration_ms: 1,
      warnings: [],
      error: "backend restarted while generating",
      last_event_id: "",
    }],
  });
  assert.equal(turns[1].status, "failed");
  assert.equal(turns[1].error, "backend restarted while generating");
  assert.equal(turns[1].requestId, undefined);
});
