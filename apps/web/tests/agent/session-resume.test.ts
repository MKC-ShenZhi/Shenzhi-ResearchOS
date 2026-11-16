import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { attachAgentSessionRun, streamAgentSessionRun } from "../../clients/backend/agent";
import { ApiError } from "../../clients/backend/http";
import { visibleNotes } from "../../features/agent-chat/timeline";

const PAGE = readFileSync("features/agent-chat/shenzhi-ai-page.tsx", "utf8");
const CLIENT = readFileSync("clients/backend/agent.ts", "utf8");

test("系统提示隐藏，插话与追问按原顺序保留，历史数据不被修改", () => {
  const notes = [
    { kind: "system", text: "预算提示" },
    { kind: "steer", text: "用户插话" },
    { kind: "system", text: "上下文已压缩" },
    { kind: "follow_up", text: "用户追问" },
  ];
  assert.deepEqual(visibleNotes(notes), [notes[1], notes[3]]);
  assert.equal(notes.length, 4);
  assert.deepEqual(visibleNotes([]), []);
  assert.match(PAGE, /visibleNotes\(turn\.steers\)\.map/);
  assert.doesNotMatch(PAGE, /onCompaction:|上下文已压缩/);
});

test("切换会话只断开订阅，显式停止按钮仍调用 stop 接口", () => {
  assert.doesNotMatch(PAGE, /stopAgentRun\(previousRunId\)/);
  assert.match(PAGE, /previousRun\.controller\.abort\(\)/);
  assert.match(PAGE, /await stopAgentRun\(runId\)/);
  assert.match(PAGE, /return \(\) => \{\s*active = false;\s*abortRef\.current\?\.abort\(\)/);
});

test("进入运行中的最后一轮时清空增量状态，复用 handlers 续接，并只刷新一次 404", () => {
  assert.match(PAGE, /const lastTurn = session\.turns\.at\(-1\)/);
  assert.match(PAGE, /lastTurn\?\.status === "running"/);
  assert.match(PAGE, /stream: initialStreamState\(\), content: "", reasoning: "", steers: \[\]/);
  assert.match(PAGE, /attachAgentSessionRun\(sessionId, buildRunHandlers\(context, controller\), controller\.signal\)/);
  assert.match(PAGE, /cause instanceof ApiError && cause\.status === 404/);
  assert.match(PAGE, /const refreshed = await getAgentSession\(sessionId\)/);
  assert.equal((PAGE.match(/const refreshed = await getAgentSession\(sessionId\)/g) ?? []).length, 1);
  assert.match(PAGE, /refreshed\.turns\.at\(-1\)\?\.status === "running"/);
  assert.match(PAGE, /当前连接无法接续/);
  assert.match(PAGE, /active && isCurrentRun\(context, controller\) && !controller\.signal\.aborted/);
  assert.doesNotMatch(PAGE, /AbortError[^}]*stopped: true/);
  assert.match(PAGE, /finishRun\(context, controller\)/);
});

test("新 Agent 提交生成新操作键，显式重试才沿用原键", () => {
  assert.match(PAGE, /retryOperationKey \?\? newTurnId\("operation"\)/);
  assert.match(PAGE, /retryPendingOperation/);
  assert.match(PAGE, /operation\.body, operation\.key/);
  assert.doesNotMatch(PAGE, /pendingOperation\?\.request === request/);
  assert.match(PAGE, /onCompleted\?\.\(\)/);
});

test("Agent 网络重试复用同一组乐观消息行", () => {
  assert.match(PAGE, /userId: string; assistantId: string/);
  assert.match(PAGE, /const retry = retryOperationKey && pendingOperationRef\.current\?\.key === retryOperationKey/);
  assert.match(PAGE, /pendingOperationRef\.current = \{ sessionId, body: requestBody, key: idempotencyKey, userId, assistantId \}/);
  assert.match(PAGE, /turn\.id === assistantId/);
});

test("Agent 409 明确提示跨进程续接限制并保留同键重试", () => {
  assert.match(PAGE, /error instanceof ApiError && error\.status === 409[\s\S]*?当前连接无法实时续接/);
  assert.match(PAGE, /operation\.body, operation\.key/);
  assert.match(PAGE, /pendingOperationRef\.current = null/);
});

test("客户端导出 GET 续接入口并与新发送共享事件分发", async () => {
  assert.match(CLIENT, /export async function attachAgentSessionRun/);
  assert.match(CLIENT, /\/run\/stream\?after=0/);
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; method?: string; body?: BodyInit | null; headers?: HeadersInit }> = [];
  const events = [
    ["run_start", { run_id: "run-replay" }],
    ["meta", { warnings: ["提示"] }],
    ["delta", { text: "答案", reasoning: "思考", turn: 1 }],
    ["message", { text: "插话", kind: "steer" }],
    ["compaction", { before_chars: 100, after_chars: 10 }],
    ["tool_call", { tool_call_id: "t1", name: "echo", arguments: "{}", turn: 1 }],
    ["tool_end", { tool_call_id: "t1", is_error: false, duration_ms: 5, summary: "完成" }],
    ["result", { status: "done", final_text: "答案", turns: 1, duration_ms: 10 }],
  ] as const;
  globalThis.fetch = async (url, options) => {
    requests.push({ url: String(url), method: options?.method, body: options?.body, headers: options?.headers });
    return new Response(events.map(([name, data], index) =>
      `id: ${index}\nevent: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("") + ": ping\n\n", {
      headers: { "Content-Type": "text/event-stream" },
    });
  };
  try {
    const received: unknown[][] = [];
    const handlers: Parameters<typeof attachAgentSessionRun>[1] = {
      onRunStart: (...args) => { received.push(["run_start", ...args]); },
      onDelta: (...args) => { received.push(["delta", ...args]); },
      onMeta: (...args) => { received.push(["meta", ...args]); },
      onMessage: (...args) => { received.push(["message", ...args]); },
      onCompaction: (...args) => { received.push(["compaction", ...args]); },
      onToolCall: (...args) => { received.push(["tool_call", ...args]); },
      onToolEnd: (...args) => { received.push(["tool_end", ...args]); },
      onResult: (...args) => { received.push(["result", ...args]); },
    };
    await attachAgentSessionRun("session/encoded", handlers);
    assert.equal(requests[0].url, "/api/v1/agent/sessions/session%2Fencoded/run/stream?after=0");
    assert.equal(requests[0].method, "GET");
    assert.equal(requests[0].body, undefined);
    assert.deepEqual(received.map(([name]) => name), events.map(([name]) => name));
    const replayed = [...received];
    received.length = 0;
    await streamAgentSessionRun("session/encoded", {
      prompt: "提问", mode: "fast", attachments: [], skills: [],
    }, handlers, "agent-operation-1");
    assert.equal(requests[1].method, "POST");
    assert.equal(new Headers(requests[1].headers).get("Idempotency-Key"), "agent-operation-1");
    assert.deepEqual(received, replayed);
    globalThis.fetch = async () => new Response(null, { status: 404 });
    await assert.rejects(attachAgentSessionRun("missing", handlers),
      (error: unknown) => error instanceof ApiError && error.status === 404);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
