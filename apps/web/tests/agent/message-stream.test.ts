import assert from "node:assert/strict";
import test from "node:test";
import {
  attachAgentSessionRun, getAgentSession, streamAgentRun, streamAgentSessionRun,
  type AgentRunResult, type AgentStoredTurn, type AgentSessionDetail,
} from "../../clients/backend/agent";
import { AgentMessageProtocolError } from "../../clients/backend/agent-message";
import { applyMessageEvent, initialMessageState, reconcileMessage, startMessageRun } from "../../features/agent-chat/message-state";
import { sessionExportMessages } from "../../features/agent-chat/session-export";
import { storedTurns } from "../../features/agent-chat/session-state";
import { applyDelta, initialStreamState } from "../../features/agent-chat/timeline";
import { messageEvents, messageFixture, mockSse, type MockMessageEvent } from "./message-fixtures";

function result(message = messageFixture()): AgentRunResult {
  assert.notEqual(message.status, "running");
  return { status: message.status as AgentRunResult["status"], final_text: "旧正文", message, turns: 2, duration_ms: 9 };
}

function storedTurn(message: AgentStoredTurn["message"]): AgentStoredTurn {
  return {
    id: "turn1", user_content: "q", assistant_content: "旧正文", reasoning: "思考",
    message, status: "done", settings: {}, sources: [{ title: "旧来源" }], warnings: [],
    stopped: false, process: [{ kind: "reasoning", text: "思考" }], steers: [], usage: {}, created_at: 1,
  };
}

test("mock fragmented SSE assembles all blocks before message_end across POST, GET and stateless clients", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const message = messageFixture();
  const wire: MockMessageEvent[] = [
    { id: "0", event: "run_start", data: { run_id: "r1" } },
    { id: "1", event: "delta", data: { text: "旧正文", reasoning: "思考", turn: 1 } },
    ...messageEvents(message),
    { id: "last", event: "result", data: result(message) },
  ].map((event, index) => ({ ...event, id: String(index) }));
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init });
    // Replay one delta with the same ID: structured state must append it once.
    const duplicate = wire.findIndex((event) => event.event === "block_delta");
    return mockSse([...wire.slice(0, duplicate + 1), wire[duplicate], ...wire.slice(duplicate + 1)]);
  };
  try {
    for (const endpoint of ["session-post", "session-get", "stateless"] as const) {
      let state = initialMessageState();
      let timeline = initialStreamState();
      let legacy = "";
      let receivedResult = false;
      const receivedIds: string[] = [];
      const handlers: Parameters<typeof attachAgentSessionRun>[1] = {
        onRunStart: (runId) => { state = startMessageRun(state, runId); },
        onMessageEvent: (event) => {
          receivedIds.push(event.id!);
          if (event.event === "message_end") {
            assert.deepEqual(state.message?.blocks, message.blocks);
            assert.deepEqual(state.message?.references, message.references);
          }
          state = applyMessageEvent(state, event);
        },
        onDelta: (text, reasoning, turn) => {
          legacy += text;
          timeline = applyDelta(timeline, text, reasoning, turn);
        },
        onMeta() {}, onToolCall() {}, onToolEnd() {},
        onResult: (received) => {
          assert.deepEqual(received.message, message);
          state = reconcileMessage(state, received.message);
          receivedResult = true;
        },
      };
      if (endpoint === "session-post") {
        await streamAgentSessionRun("s/1", { prompt: "q", mode: "fast", skills: [], attachments: [] }, handlers, "same-operation-key");
      } else if (endpoint === "session-get") {
        await attachAgentSessionRun("s/1", handlers);
      } else {
        await streamAgentRun({ prompt: "q" }, handlers);
      }
      assert.equal(receivedResult, true);
      assert.deepEqual(state.message, message);
      assert.equal(legacy, "旧正文");
      assert.deepEqual(timeline.entries.map((entry) => entry.kind), ["thinking", "text"]);
      assert.ok(receivedIds.includes("2"));
    }
    assert.equal(requests[0].init?.method, "POST");
    assert.equal(new Headers(requests[0].init?.headers).get("Idempotency-Key"), "same-operation-key");
    assert.equal(requests[1].url, "/api/v2/agent/sessions/s%2F1/run/stream?after=0");
    assert.equal(requests[1].init?.method, "GET");
    assert.equal(requests[2].url, "/api/v2/agent/run");
  } finally { globalThis.fetch = originalFetch; }
});

test("mock history restores the exact same message as streaming, keeping legacy turns readable", async () => {
  const originalFetch = globalThis.fetch;
  const turns = [storedTurn(messageFixture()), { ...storedTurn(null), id: "old-null" },
    { ...storedTurn(undefined), id: "old-omitted" }];
  delete turns[2].message;
  const session: AgentSessionDetail = { id: "s1", title: "mock", created_at: 1, updated_at: 2, settings: {}, turns };
  globalThis.fetch = async (url) => {
    assert.equal(String(url), "/api/v2/agent/sessions/s1");
    return Response.json({ code: 0, data: session });
  };
  try {
    const received = await getAgentSession("s1");
    assert.deepEqual(received, session);
    const restored = storedTurns(received.turns);
    assert.deepEqual(restored[1].structured.message, messageFixture());
    assert.equal(restored[1].content, "旧正文");
    assert.deepEqual(restored[1].sources, [{ title: "旧来源" }]);
    assert.equal(restored[3].structured.message, null);
    assert.equal(restored[5].structured.message, null);
    assert.equal(Object.hasOwn(received.turns[2], "message"), false);
    restored[1].structured.message!.blocks[0].content = "consumer mutation";
    assert.deepEqual(received.turns[0].message, messageFixture());
  } finally { globalThis.fetch = originalFetch; }
});

test("mock EOF or malformed structured event retains the last valid partial blocks", async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const malformed of [false, true]) {
      let state = initialMessageState();
      const prefix = messageEvents().slice(0, 5);
      const wire = malformed ? [...prefix, { id: "5", event: "block_delta", data: { message_id: "msg_mock", block_id: "b2", delta: 123 } }] : prefix;
      globalThis.fetch = async () => mockSse(wire);
      await assert.rejects(attachAgentSessionRun("s1", {
        onMessageEvent: (event) => { state = applyMessageEvent(state, event); },
        onDelta() {}, onMeta() {}, onToolCall() {}, onToolEnd() {},
        onResult() { assert.fail("no terminal result was sent"); },
      }), malformed ? AgentMessageProtocolError : /连接已中断/);
      assert.equal(state.message?.blocks[0].content, messageFixture().blocks[0].content.slice(0, 23));
      assert.equal(state.message?.status, "running");
      assert.equal(state.ended, false);
    }
  } finally { globalThis.fetch = originalFetch; }
});

test("mock final result alone calibrates the message and invalid history is rejected", async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const status of ["done", "failed", "stopped", "timeout", "awaiting_input"] as const) {
      const message = messageFixture(status);
      let state = initialMessageState();
      globalThis.fetch = async () => mockSse([{ id: "0", event: "result", data: result(message) }]);
      await attachAgentSessionRun("s1", {
        onDelta() {}, onMeta() {}, onToolCall() {}, onToolEnd() {},
        onResult: (received) => { state = reconcileMessage(state, received.message); },
      });
      assert.deepEqual(state.message, message);
      assert.equal(state.ended, true);
    }
    for (const invalid of ["references", "status"]) {
      const message = messageFixture(invalid === "status" ? "failed" : "done");
      if (invalid === "references") message.references = [];
      globalThis.fetch = async () => Response.json({ code: 0, data: {
        id: "s1", turns: [storedTurn(message)],
      } });
      await assert.rejects(getAgentSession("s1"), AgentMessageProtocolError);
    }
  } finally { globalThis.fetch = originalFetch; }
});

test("mock v2 versioned events and result keep the nested message unchanged", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => mockSse([
    ...messageEvents().map((event) => ({ ...event, data: { ...event.data as object, schema_version: 1 } })),
    { id: "100", event: "result", data: { ...result(), schema_version: 1 } },
  ]);
  let state = initialMessageState();
  try {
    await attachAgentSessionRun("s1", {
      onMessageEvent: (event) => { state = applyMessageEvent(state, event); },
      onDelta() {}, onMeta() {}, onToolCall() {}, onToolEnd() {},
      onResult: (received) => { state = reconcileMessage(state, received.message); },
    });
    assert.deepEqual(state.message, messageFixture());
  } finally { globalThis.fetch = originalFetch; }
});


test("explicit rejected final snapshot clears streamed presentation for text fallback", () => {
  const state = reconcileMessage(initialMessageState(), messageFixture());
  assert.equal(reconcileMessage(state, null, true).message, null);
  assert.deepEqual(reconcileMessage(state, undefined).message, state.message);
});


test("export projection keeps every block/reference and includes structured-only turns", () => {
  const message = messageFixture();
  const turns = storedTurns([{ ...storedTurn(message), assistant_content: "" }, storedTurn(null)]);
  const exported = sessionExportMessages(turns);
  assert.equal(exported.length, 4);
  assert.deepEqual(exported[1].message, message);
  const jsonl = exported.map((entry) => JSON.stringify(entry)).join("\n");
  assert.deepEqual(JSON.parse(jsonl.split("\n")[1]).message, message);
  assert.equal(exported[3].content, "旧正文");
});
