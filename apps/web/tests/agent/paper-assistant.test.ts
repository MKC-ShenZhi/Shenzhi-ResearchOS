import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { AgentRunResult } from "../../clients/backend/agent";
import {
  initialPaperAgentState,
  paperAgentHistory,
  paperAgentReducer,
  paperAgentRunRequest,
  type PaperAgentState,
} from "../../features/papers/[id]/paper-agent";

const paper = { id: "paper:current-123", title: "Current Paper" };

function startedState(): PaperAgentState {
  return paperAgentReducer(initialPaperAgentState(paper.id), {
    type: "start",
    question: "这篇论文的核心方法是什么？",
    userId: "user-1",
    assistantId: "assistant-1",
  });
}

function result(overrides: Partial<AgentRunResult> = {}): AgentRunResult {
  return {
    status: "done",
    final_text: "核心方法见第 3 页。",
    turns: 2,
    duration_ms: 10,
    ...overrides,
  };
}

test("Paper Assistant uses the Agent client instead of the legacy Chat session", () => {
  const component = readFileSync("features/papers/[id]/components/paper-assistant-panel.tsx", "utf8");
  const hook = readFileSync("features/papers/[id]/use-paper-agent.ts", "utf8");

  assert.match(component, /usePaperAgent\(paper\)/);
  assert.doesNotMatch(component, /useChatSession|attachments:\s*\[\{\s*kind:\s*["']paper/);
  assert.match(hook, /streamAgentRun\(/);
});

test("Paper Agent request binds the exact paper id while the visible user turn stays unwrapped", () => {
  const question = "这篇论文的核心贡献是什么？";
  const state = paperAgentReducer(initialPaperAgentState(paper.id), {
    type: "start",
    question,
    userId: "user-1",
    assistantId: "assistant-1",
  });
  const request = paperAgentRunRequest(paper, question, []);

  assert.equal(state.turns[0].content, question);
  assert.doesNotMatch(state.turns[0].content, /paper_id|read_paper/);
  assert.match(request.prompt, /paper_id: paper:current-123/);
  assert.match(request.prompt, /read_paper/);
  assert.ok(request.prompt.includes(question));
});

test("Paper Agent history follows the existing user/assistant protocol across turns", () => {
  let state = startedState();
  state = paperAgentReducer(state, {
    type: "result",
    assistantId: "assistant-1",
    result: result(),
  });

  assert.deepEqual(paperAgentHistory(state.turns), [
    { kind: "user", text: "这篇论文的核心方法是什么？" },
    {
      kind: "assistant",
      content: "核心方法见第 3 页。",
      reasoning: "",
      tool_calls: [],
      stop_reason: "stop",
    },
  ]);

  const followUp = paperAgentRunRequest(paper, "这个方法具体怎么实现？", state.turns);
  assert.deepEqual(followUp.history, paperAgentHistory(state.turns));
  assert.match(followUp.prompt, /paper_id: paper:current-123/);
});

test("Agent stream deltas update the active Assistant answer", () => {
  let state = startedState();
  state = paperAgentReducer(state, { type: "delta", assistantId: "assistant-1", text: "核心", turn: 2 });
  state = paperAgentReducer(state, { type: "delta", assistantId: "assistant-1", text: "方法", turn: 2 });
  assert.equal(state.turns[1].content, "核心方法");

  state = paperAgentReducer(state, { type: "delta", assistantId: "assistant-1", text: "最终回答", turn: 3 });
  assert.equal(state.turns[1].content, "最终回答");
});

test("Agent failures and aborts always leave the running state", () => {
  const failed = paperAgentReducer(startedState(), {
    type: "failure",
    assistantId: "assistant-1",
    message: "连接失败",
    requestId: "request-1",
    aborted: false,
  });
  assert.equal(failed.running, false);
  assert.equal(failed.turns[1].status, "error");
  assert.equal(failed.turns[1].error, "连接失败");
  assert.equal(failed.turns[1].requestId, "request-1");

  const aborted = paperAgentReducer(startedState(), {
    type: "failure",
    assistantId: "assistant-1",
    aborted: true,
  });
  assert.equal(aborted.running, false);
  assert.equal(aborted.turns[1].status, "stopped");
  assert.equal(aborted.turns[1].error, undefined);
});

test("read_paper tool failure remains visible instead of implying that the PDF was read", () => {
  let state = startedState();
  state = paperAgentReducer(state, { type: "read_paper_start" });
  assert.equal(state.activity, "reading_pdf");
  state = paperAgentReducer(state, {
    type: "read_paper_end",
    assistantId: "assistant-1",
    failed: true,
    stillReading: false,
  });
  assert.equal(state.activity, null);
  assert.match(state.turns[1].warnings[0], /PDF 读取失败/);
});

test("switching papers clears the previous paper conversation and binding", () => {
  const previous = startedState();
  const next = paperAgentReducer(previous, { type: "reset", paperId: "paper:next-456" });
  const request = paperAgentRunRequest({ id: next.paperId, title: "Next Paper" }, "这篇论文讲什么？", next.turns);

  assert.equal(next.paperId, "paper:next-456");
  assert.deepEqual(next.turns, []);
  assert.match(request.prompt, /paper_id: paper:next-456/);
  assert.doesNotMatch(request.prompt, /paper:current-123/);
});
