import assert from "node:assert/strict";
import test from "node:test";
import { quotedPromptParts, withQuote } from "../../features/agent-chat/quoted-prompt";
import { storedTurns } from "../../features/agent-chat/session-state";
import { sessionExportMessages } from "../../features/agent-chat/session-export";
import type { AgentStoredTurn } from "../../clients/backend/agent";

test("quote presentation keeps the user's question separate from complete model context", () => {
  const quote = "成本与算力结构在变\n\n第二个段落。";
  const question = "这个如何理解\n请举个例子。";
  const prompt = withQuote(question, { text: quote });
  assert.equal(prompt, `针对之前回答中的这段内容：\n\n${quote}\n\n我的问题/意见是：${question}`);
  assert.deepEqual(quotedPromptParts(prompt), { question, quote });
  assert.equal(withQuote(question, null), question);
});

test("plain messages and incomplete quote envelopes retain their original text", () => {
  for (const text of ["这个如何理解", "我的问题/意见是：如何理解", "介绍：针对之前回答中的这段内容：\n\n示例", "针对之前回答中的这段内容：\n\n内容", "针对之前回答中的这段内容：\n\n\n\n我的问题/意见是：问题", "针对之前回答中的这段内容：\n\n内容\n\n我的问题/意见是："]) {
    assert.deepEqual(quotedPromptParts(text), { question: text });
  }
});

test("a quoted fragment containing the legacy separator is preserved", () => {
  const quote = "引用了格式：\n\n我的问题/意见是：示例问题";
  assert.deepEqual(quotedPromptParts(withQuote("这个格式是什么", { text: quote })), {
    question: "这个格式是什么", quote,
  });
});

test("history hydration and export preserve raw context while presentation recovers original question", () => {
  const prompt = withQuote("这个如何理解", { text: "成本与算力结构在变" });
  const stored: AgentStoredTurn = {
    id: "quoted-history", user_content: prompt, assistant_content: "回答", reasoning: "", process: [],
    steers: [], sources: [], warnings: [], stopped: false, status: "done", settings: {}, usage: {}, created_at: 1,
  };
  const turns = storedTurns([stored]);
  assert.equal(turns[0].content, prompt);
  assert.deepEqual(quotedPromptParts(turns[0].content), { question: "这个如何理解", quote: "成本与算力结构在变" });
  assert.equal(sessionExportMessages(turns)[0].text, prompt);
});
