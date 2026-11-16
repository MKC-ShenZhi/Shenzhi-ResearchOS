/**
 * 过程流（"思考 → 工具 → 思考"）的回归测试。
 *
 * 断言直接对应实测出现过的事故：
 *  1. 工具轮之间的孤立标点不能出现在对话里（"对话框里孤零零一个句点"）；
 *  2. 每轮思考必须独立，不能把前面几轮的思考重复粘贴（"4 段开头逐字相同"）；
 *  3. 思考与正文各自独立成条目（pi 的内容块模型），工具条目与它们并列交错；
 *  4. 工具结果要回填到同一个工具对象（否则行永远转圈）。
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  applyDelta, applyToolCall, applyToolEnd, initialStreamState, isMeaningful,
  previewLine, renderEntries, restoreEntries,
  type Activity, type Entry, type StreamState,
} from "../../features/agent-chat/timeline";

const tool = (toolCallId: string, name: string): Activity =>
  ({ toolCallId, name, arguments: "{}", done: false, isError: false, durationMs: 0 });

function feed(state: StreamState, events: Array<[string, string, number]>): StreamState {
  return events.reduce((acc, [text, reasoning, turn]) => applyDelta(acc, text, reasoning, turn), state);
}

/** 渲染序列的紧凑表示（思考用 ~，正文用 >，工具用 $），便于断言顺序与归属。 */
function shape(state: StreamState): string[] {
  return renderEntries(state).map((entry: Entry) => {
    if (entry.kind === "tool") return `$${entry.tool.name}`;
    return `${entry.kind === "thinking" ? "~" : ">"}${entry.text}`;
  });
}

test("isMeaningful：纯标点/空白不算内容", () => {
  for (const fragment of [".", "。", "..", "...", " ", "\n", "-", "—", "！？"]) {
    assert.equal(isMeaningful(fragment), false, `${JSON.stringify(fragment)} 应判为无意义`);
  }
  for (const fragment of ["1", "a", "RAG", "用户", "好的，用户需要"]) {
    assert.equal(isMeaningful(fragment), true, `${JSON.stringify(fragment)} 应判为有意义`);
  }
});

test("思考与正文各自独立成条目，工具并列交错（pi 的内容块模型）", () => {
  let state = initialStreamState();
  state = feed(state, [["我先查知识库。", "The user", 1]]);
  state = applyToolCall(state, tool("c1", "read_skill"));
  state = feed(state, [["资料够了。", "I should look closer", 2]]);
  state = applyToolCall(state, tool("c2", "paper_search"));
  state = feed(state, [["最终答案。", "Now synthesize", 3]]);

  assert.deepEqual(shape(state), [
    "~The user", ">我先查知识库。",
    "$read_skill",
    "~I should look closer", ">资料够了。",
    "$paper_search",
    "~Now synthesize", ">最终答案。",
  ]);
});

test("每轮思考独立，不重复粘贴前几轮（事故 2）", () => {
  let state = initialStreamState();
  state = feed(state, [["", "The user", 1]]);
  state = applyToolCall(state, tool("c1", "read_skill"));
  state = feed(state, [["", "I should look closer", 2]]);
  state = applyToolCall(state, tool("c2", "paper_search"));
  state = feed(state, [["", "Now synthesize", 3]]);

  const thinking = renderEntries(state)
    .filter((entry) => entry.kind === "thinking")
    .map((entry) => (entry.kind === "thinking" ? entry.text : ""));
  assert.deepEqual(thinking, ["The user", "I should look closer", "Now synthesize"]);
});

test("text 与 reasoning 都是增量片，各自按片拼接", () => {
  // 后端 runtime.py:531-539：两者发的都是增量，累计在客户端完成
  let state = initialStreamState();
  state = feed(state, [["", "The", 1], ["", " user", 1], ["Hello", "", 1], [" world", "", 1]]);
  assert.deepEqual(shape(state), ["~The user", ">Hello world"]);
});

test("工具轮之间的孤立标点不显示（事故 1）", () => {
  let state = initialStreamState();
  state = feed(state, [["", "The user", 1], [".", "", 1]]);
  state = applyToolCall(state, tool("c1", "read_skill"));
  state = feed(state, [["", "Next", 2], [".", "", 2]]);
  state = applyToolCall(state, tool("c2", "paper_search"));
  state = feed(state, [["", "Final", 3], ["Answer here.", "", 3]]);

  const texts = renderEntries(state)
    .filter((entry) => entry.kind === "text")
    .map((entry) => (entry.kind === "text" ? entry.text : ""));
  assert.deepEqual(texts, ["Answer here."], "纯标点的正文轮次不出现");
});

test("没有可见内容的条目完全不渲染", () => {
  let state = feed(initialStreamState(), [["", ".", 1]]);
  assert.deepEqual(renderEntries(state), []);
  state = applyToolCall(state, tool("c1", "read_skill"));
  assert.deepEqual(shape(state), ["$read_skill"]);
});

test("工具结束回填到同一个工具对象（事故 4）", () => {
  let state = applyToolCall(initialStreamState(), tool("c1", "paper_search"));
  state = applyToolEnd(state, "c1", { done: true, durationMs: 5672 });
  const entry = renderEntries(state)[0];
  assert.equal(entry.kind, "tool");
  if (entry.kind === "tool") {
    assert.equal(entry.tool.done, true);
    assert.equal(entry.tool.durationMs, 5672);
  }
});

test("工具之后的正文落到工具之后，不串到思考前面", () => {
  let state = feed(initialStreamState(), [["", "先想一下", 1]]);
  state = applyToolCall(state, tool("c1", "paper_search"));
  state = feed(state, [["结果拿到了。", "", 1]]);
  assert.deepEqual(shape(state), ["~先想一下", "$paper_search", ">结果拿到了。"]);
});

test("旧会话（segments/activity）能折算成交错条目", () => {
  const entries = restoreEntries([
    { kind: "reasoning", text: "旧思考" },
    { kind: "tool", tool: tool("c1", "read_skill") },
  ], undefined);
  assert.deepEqual(entries.map((entry) => entry.kind), ["thinking", "tool"]);

  const fromActivity = restoreEntries(undefined, [tool("c1", "read_skill")]);
  assert.deepEqual(fromActivity.map((entry) => entry.kind), ["tool"]);
});

test("previewLine 压平空白并截断", () => {
  assert.equal(previewLine("a\n\nb"), "a b");
  assert.equal(previewLine("x".repeat(100)).length, 81);
});
