import assert from "node:assert/strict";
import test from "node:test";
import { AgentMessageProtocolError, parseAgentMessage, parseAgentMessageEvent } from "../../clients/backend/agent-message";
import {
  applyMessageEvent, initialMessageState, reconcileMessage, startMessageRun, type AgentMessageState,
} from "../../features/agent-chat/message-state";
import { initialPaperAgentState, paperAgentReducer } from "../../features/papers/[id]/paper-agent";
import { messageEvents, messageFixture, type MockMessageEvent } from "./message-fixtures";

function apply(state: AgentMessageState, event: MockMessageEvent): AgentMessageState {
  const parsed = parseAgentMessageEvent({ ...event, data: JSON.stringify(event.data) });
  assert.ok(parsed);
  return applyMessageEvent(state, parsed);
}

test("message protocol preserves Markdown, metadata, nulls and omitted fields", () => {
  const message = messageFixture();
  assert.deepEqual(parseAgentMessage(message), message);
  assert.equal(Object.hasOwn(parseAgentMessage(message).references[1], "authors"), false);
  assert.equal(parseAgentMessage(message).references[0].url, null);
  assert.equal(parseAgentMessageEvent({ event: "delta", data: "{}" }), null);
});

test("malformed snapshots and duplicate IDs are rejected; unknown blocks stay opaque", () => {
  const message = messageFixture();
  for (const payload of [
    { ...message, schema_version: 2 }, { ...message, created_at: Infinity },
    { ...message, references: [] }, { ...message, blocks: [message.blocks[0], message.blocks[0]] },
    { ...message, references: [...message.references, message.references[0]] },
    { ...message, blocks: [{ id: "broken", type: "markdown", content: 123 }] },
    { ...message, metadata: [] },
  ]) assert.throws(() => parseAgentMessage(payload), AgentMessageProtocolError);
  const unknown = { id: "unsupported", type: "future-type", data: { value: 1 } };
  assert.deepEqual(parseAgentMessage({ ...message, blocks: [unknown] }).blocks, [unknown]);
  assert.throws(() => parseAgentMessage(message, "failed"), AgentMessageProtocolError);
  assert.throws(() => parseAgentMessageEvent({ event: "block_delta", data: '{"delta":1}' }), AgentMessageProtocolError);
  assert.throws(() => parseAgentMessageEvent({ event: "message_end", data: JSON.stringify({ message: { ...message, status: "running" } }) }), AgentMessageProtocolError);
});

test("all blocks and references assemble correctly before the final snapshot arrives", () => {
  const message = messageFixture();
  const events = messageEvents(message);
  let state = startMessageRun(initialMessageState(), "r1");
  for (const event of events.slice(0, -1)) state = apply(state, event);
  assert.deepEqual(state.message?.blocks, message.blocks);
  assert.deepEqual(state.message?.references, message.references);
  assert.equal(state.message?.status, "running");
  assert.equal(state.activeBlockId, null);
  assert.equal(state.ended, false);
  const before = structuredClone(state);
  state = apply(state, events.at(-1)!);
  assert.deepEqual(state.message, message);
  assert.equal(state.ended, true);
  assert.deepEqual(before.message?.blocks, message.blocks);
});

test("replayed event IDs do not duplicate blocks, deltas or references", () => {
  const events = messageEvents();
  let state = startMessageRun(initialMessageState(), "r1");
  for (const event of events.slice(0, 7)) {
    state = apply(state, event);
    const once = state;
    state = apply(state, event);
    assert.equal(state, once);
  }
  // Reconnect from zero with the current partial state; duplicate run_start is harmless.
  assert.equal(startMessageRun(state, "r1"), state);
  for (const event of events) state = apply(state, event);
  assert.deepEqual(state.message, messageFixture());
  const complete = state;
  for (const event of events) state = apply(state, event);
  assert.equal(state, complete);
});

test("upsert replaces a reference in place and a new Run cannot inherit prior blocks", () => {
  let state = messageEvents().slice(0, 3).reduce(apply, startMessageRun(initialMessageState(), "r1"));
  state = apply(state, { id: "3", event: "reference_upsert", data: {
    message_id: "msg_mock", reference: { ...messageFixture().references[0], title: "补全标题", authors: ["新作者"] },
  } });
  assert.deepEqual(state.message?.references.map((reference) => reference.id), ["r2", "r1"]);
  assert.equal(state.message?.references[0].title, "补全标题");
  state = startMessageRun(state, "r2");
  assert.equal(state.message, null);
  assert.equal(state.lastEventId, null);
  state = messageEvents(messageFixture("failed", "msg_retry")).reduce(apply, state);
  assert.deepEqual(state.message, messageFixture("failed", "msg_retry"));
});

test("bad associations or order retain valid content and final snapshots repair state", () => {
  let state = messageEvents().slice(0, 5).reduce(apply, initialMessageState());
  const partial = structuredClone(state.message);
  const stale = apply(state, { id: "10", event: "block_delta", data: { message_id: "old_message", block_id: "b2", delta: "wrong" } });
  assert.equal(stale, state);
  state = apply(state, { id: "10", event: "block_delta", data: { message_id: "msg_mock", block_id: "missing", delta: "wrong" } });
  assert.deepEqual(state.message, partial);
  assert.ok(state.protocolError);
  state = apply(state, { id: "11", event: "block_start", data: { message_id: "msg_mock", block: { id: "overlap", type: "markdown", content: "wrong" } } });
  assert.deepEqual(state.message, partial);
  state = apply(state, { ...messageEvents().at(-1)!, id: "12" });
  assert.deepEqual(state.message, messageFixture());
  assert.equal(state.protocolError, null);
  assert.equal(apply(state, { id: "13", event: "block_delta", data: { message_id: "msg_mock", block_id: "b1", delta: "late" } }), state);
});

test("reference arrival can follow deltas and citation markers can span deltas", () => {
  const message = messageFixture();
  let state = apply(initialMessageState(), messageEvents()[0]);
  state = apply(state, { id: "1", event: "block_start", data: { message_id: message.id, block: { id: "b", type: "markdown", content: "" } } });
  for (const [index, delta] of ["结果 [[ci", "te:r2", "]]"].entries()) {
    state = apply(state, { id: String(index + 2), event: "block_delta", data: { message_id: message.id, block_id: "b", delta } });
  }
  state = apply(state, { id: "5", event: "reference_upsert", data: { message_id: message.id, reference: message.references[0] } });
  assert.equal(state.message?.blocks[0].content, "结果 [[cite:r2]]");
  assert.equal(state.message?.references[0].id, "r2");
});

test("terminal snapshots replace partial state instead of appending; legacy results retain it", () => {
  let state = messageEvents().slice(0, 5).reduce(apply, initialMessageState());
  assert.equal(reconcileMessage(state, null), state);
  assert.equal(reconcileMessage(state, undefined), state);
  for (const status of ["done", "failed", "stopped", "timeout", "awaiting_input"] as const) {
    const final = messageFixture(status);
    const once = reconcileMessage(state, final);
    assert.deepEqual(once.message, final);
    assert.deepEqual(reconcileMessage(once, final).message, final);
    final.blocks[0].content = "consumer mutation";
    assert.deepEqual(once.message, messageFixture(status));
  }
  const message = messageFixture();
  state = reconcileMessage(state, message);
  message.references[0].authors?.reverse();
  assert.deepEqual(state.message, messageFixture());
});

test("Paper Agent reuses Block assembly without changing its legacy content or rendered state", () => {
  let state = paperAgentReducer(initialPaperAgentState("p1"), { type: "start", question: "q", userId: "u1", assistantId: "a1" });
  state = paperAgentReducer(state, { type: "run_start", assistantId: "a1", runId: "r1" });
  for (const event of messageEvents().slice(0, -1)) {
    const parsed = parseAgentMessageEvent({ ...event, data: JSON.stringify(event.data) })!;
    state = paperAgentReducer(state, { type: "message_event", assistantId: "a1", event: parsed });
  }
  assert.deepEqual(state.turns[1].structured?.message?.blocks, messageFixture().blocks);
  assert.equal(state.turns[1].content, "");
  state = paperAgentReducer(state, { type: "result", assistantId: "a1", result: {
    status: "done", final_text: "旧正文", message: messageFixture(), turns: 1, duration_ms: 9,
  } });
  assert.equal(state.turns[1].content, "旧正文");
  assert.deepEqual(state.turns[1].structured?.message, messageFixture());
});
