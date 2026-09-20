import assert from "node:assert/strict";
import { test } from "node:test";

import { streamAgentRun } from "../../clients/backend/agent";

test("Agent run POSTs its payload and dispatches the complete SSE loop", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const seen: string[] = [];
  const events = [
    ["run_start", { run_id: "run-1" }],
    ["delta", { text: "", reasoning: "思考", turn: 1 }],
    ["tool_call", { tool_call_id: "call-1", name: "paper_search", arguments: "{}", turn: 1 }],
    ["tool_end", { tool_call_id: "call-1", is_error: false, duration_ms: 8, summary: "找到论文" }],
    ["message", { text: "补充要求", kind: "steer" }],
    ["compaction", { before_chars: 100, after_chars: 40 }],
    ["meta", { warnings: ["提示"] }],
    ["delta", { text: "完成", reasoning: "", turn: 2 }],
    ["result", { status: "done", final_text: "完成" }],
  ] as const;
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""), {
      headers: { "content-type": "text/event-stream" },
    });
  };
  try {
    await streamAgentRun({ prompt: "检索论文", history: [], skills: [] }, {
      onRunStart: (id) => seen.push(`start:${id}`),
      onDelta: (text, reasoning, turn) => seen.push(`delta:${turn}:${text}:${reasoning}`),
      onToolCall: (tool) => seen.push(`call:${tool.name}`),
      onToolEnd: (_id, error, _ms, summary) => seen.push(`end:${error}:${summary}`),
      onMessage: (_text, kind) => seen.push(`message:${kind}`),
      onCompaction: () => seen.push("compaction"),
      onMeta: () => seen.push("meta"),
      onResult: (result) => seen.push(`result:${result.final_text}`),
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/v1/agent/run");
  assert.equal(requests[0].init?.method, "POST");
  assert.deepEqual(JSON.parse(String(requests[0].init?.body)), {
    prompt: "检索论文", history: [], skills: [],
  });
  assert.deepEqual(seen, [
    "start:run-1", "delta:1::思考", "call:paper_search", "end:false:找到论文",
    "message:steer", "compaction", "meta", "delta:2:完成:", "result:完成",
  ]);
});
