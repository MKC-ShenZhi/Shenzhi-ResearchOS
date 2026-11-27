import assert from "node:assert/strict";
import test from "node:test";
import { canShowMessageActions, messageCopyText, toggleFeedback, type MessageFeedback } from "../../features/agent-chat/components/message-actions-state";
import { messageFixture } from "./message-fixtures";

test("copy preserves ordered Markdown blocks, code, tables and whitespace", () => {
  const message = messageFixture();
  assert.equal(messageCopyText(message, "legacy duplicate"), message.blocks.map((block) => block.content).join("\n\n"));
});

test("copy excludes opaque reasoning/tool blocks and never falls back over structured data", () => {
  const message = { ...messageFixture(), blocks: [
    { id: "reasoning", type: "reasoning", content: "private thinking" },
    { id: "tool", type: "tool", content: "tool output" },
    { id: "answer", type: "markdown", content: "**answer**" },
  ] };
  assert.equal(messageCopyText(message, "legacy duplicate"), "**answer**");
  assert.equal(messageCopyText({ ...message, blocks: [] }, "legacy duplicate"), "");
  assert.equal(messageCopyText(null, "# 历史回复\n\n```ts\nconst x = 1;\n```"), "# 历史回复\n\n```ts\nconst x = 1;\n```");
});

test("streaming and stale running snapshots hide actions; terminal partial answers allow copy", () => {
  assert.equal(canShowMessageActions(messageFixture(), "done", true, "answer"), false);
  assert.equal(canShowMessageActions(messageFixture("running"), "done", false, "answer"), false);
  assert.equal(canShowMessageActions(null, "running", false, "answer"), false);
  for (const status of ["done", "failed", "stopped", "timeout", "awaiting_input"] as const) {
    assert.equal(canShowMessageActions(messageFixture(status), status, false, "partial answer"), true);
  }
  assert.equal(canShowMessageActions(null, undefined, false, "legacy answer"), true);
  assert.equal(canShowMessageActions(null, "failed", false, " \n"), false);
});

test("feedback toggles, switches exclusively, and keeps independent message values", () => {
  let first: MessageFeedback = null;
  let second: MessageFeedback = null;
  first = toggleFeedback(first, "like");
  second = toggleFeedback(second, "dislike");
  assert.equal(first, "like");
  assert.equal(second, "dislike");
  first = toggleFeedback(first, "dislike");
  assert.equal(first, "dislike");
  assert.equal(toggleFeedback(first, "dislike"), null);
  assert.equal(toggleFeedback("like", "like"), null);
  assert.equal(second, "dislike");
});
