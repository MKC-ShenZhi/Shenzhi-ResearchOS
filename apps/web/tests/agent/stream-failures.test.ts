import assert from "node:assert/strict";
import test from "node:test";
import { attachAgentSessionRun } from "../../clients/backend/agent";
import { ApiError } from "../../clients/backend/http";
import { readSseStream } from "../../clients/backend/sse";

const handlers = {
  onDelta() {}, onMeta() {}, onToolCall() {}, onToolEnd() {}, onResult() {},
};

test("EOF without result is a disconnect, not task completion", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response('event: run_start\ndata: {"run_id":"r"}\n\n', {
    headers: { "content-type": "text/event-stream" },
  });
  try {
    await assert.rejects(attachAgentSessionRun("s", handlers), /连接已中断/);
  } finally { globalThis.fetch = original; }
});

test("SSE preserves readable backend errors and request IDs", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ code: 20004, message: "Agent 服务暂不可用" }), {
    status: 503, headers: { "X-Request-ID": "req-demo" },
  });
  try {
    await assert.rejects(attachAgentSessionRun("s", handlers), (error: unknown) =>
      error instanceof ApiError && error.status === 503 && error.requestId === "req-demo"
      && error.message === "Agent 服务暂不可用");
  } finally { globalThis.fetch = original; }
});

test("SSE idle deadline aborts stalled transport with a reconnect message", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (_url, init) => {
    return new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    });
  };
  try {
    await assert.rejects(readSseStream("/stream", { idleTimeoutMs: 10, onEvent() {} }),
      (error: unknown) => error instanceof ApiError && error.status === 504 && /重新连接/.test(error.message));
  } finally { globalThis.fetch = original; }
});

test("failed and timed out results are terminal events, not transport failures", async () => {
  const original = globalThis.fetch;
  try {
    for (const status of ["failed", "timeout"]) {
      let received = "";
      globalThis.fetch = async () => new Response(`event: result\ndata: ${JSON.stringify({ status, final_text: "" })}\n\n`, {
        headers: { "content-type": "text/event-stream" },
      });
      await attachAgentSessionRun("s", { ...handlers, onResult: (result) => { received = result.status; } });
      assert.equal(received, status);
    }
  } finally { globalThis.fetch = original; }
});
