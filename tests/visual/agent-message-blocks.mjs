#!/usr/bin/env node
/** Real-browser HTTP/SSE integration against a deterministic mock Backend.
 * Start Next separately, then: node tests/visual/agent-message-blocks.mjs --next http://127.0.0.1:3311 --out <artifact-directory>
 * Keeps the isolated Edge profile and screenshots; never recursively deletes files.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer, request as httpRequest } from "node:http";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { StringDecoder } from "node:string_decoder";

const arg = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index < 0 ? fallback : process.argv[index + 1];
};
const nextOrigin = new URL(arg("--next", "http://127.0.0.1:3311"));
const output = resolve(arg("--out", ".tmp-agent-message-browser"));
mkdirSync(output, { recursive: true });
const sessionId = "browser-message-fixture";
const message = {
  id: "internal_message_id", role: "assistant", status: "done", created_at: 1795651200.125, schema_version: 1,
  metadata: { model: "internal_model_name", duration_ms: 7 },
  blocks: [
    { id: "internal_block_1", type: "markdown", content: "Transformer 首次提出了完全基于注意力机制的模型架构。[[cite:paper_ref]]" },
    { id: "internal_block_2", type: "markdown", content: '## 格式验证\n\n| 项目 | 值 |\n|---|---|\n| 参数 | 42 |\n\n公式 $x^2 + y^2$。\n\n```python\nprint("ok")\n```\n\n网页说明 [[cite:web_ref]]。' },
  ],
  references: [
    { id: "web_ref", type: "webpage", title: "Transformer 模型介绍", url: "https://huggingface.co/docs/transformers" },
    { id: "unused_ref", type: "paper", title: "不应展示的未引用来源" },
    { id: "paper_ref", type: "paper", entity_id: "internal_paper_entity", title: "Attention Is All You Need",
      authors: ["Vaswani", "Shazeer", "Parmar"], year: 2017, venue: "NeurIPS", doi: "10.48550/arXiv.1706.03762", url: "https://arxiv.org/abs/1706.03762" },
  ],
};
const summary = { id: sessionId, title: "消息协议浏览器验证", created_at: 1795651200, updated_at: 1795651200, settings: {} };
let completed = false;
let finishCitation;
let finishStream;
let postCount = 0;
let streamDisconnected = false;
const failures = [];
const checks = [];
const turn = (snapshot = message) => ({
  id: "turn_browser", user_content: "请展示结构化回复", assistant_content: "不应重复显示的旧正文", reasoning: "核对资料",
  process: [{ kind: "text", text: "不应重复显示的过程正文" }], steers: [], report: null,
  sources: [{ title: "不应重复显示的旧来源" }], question: null, warnings: [], error: null,
  stopped: false, stop_reason: "stop", status: snapshot?.status ?? "done", settings: {}, usage: {},
  created_at: 1795651200, completed_at: 1795651201, message: snapshot,
});

function json(response, data) {
  response.writeHead(200, { "Content-Type": "application/json" });
  response.end(JSON.stringify(data));
}
async function mock(request, response) {
  const url = new URL(request.url, "http://mock.test");
  const path = url.pathname;
  if (path === "/api/auth/get-session") return json(response, null);
  if (path === "/api/v2/agent/config") return json(response, { code: 0, data: {
    models: [{ value: "mock/model", label: "Mock", provider: "mock", enabled: true }], default_model: "mock/model", skills: [],
    upload: { max_size_mb: 10, max_files: 3, accept: [] },
  } });
  if (path === "/api/v2/agent/sessions") return json(response, { code: 0, data: {
    sessions: [summary], next_cursor: null, has_more: false, ephemeral: true,
  } });
  if (path.endsWith(`/sessions/${sessionId}`)) return json(response, { code: 0, data: { ...summary, turns: completed ? [turn()] : [] } });
  if (path.endsWith("/sessions/legacy-browser")) return json(response, { code: 0, data: {
    ...summary, id: "legacy-browser", turns: [{ ...turn(null), assistant_content: "旧会话仍可阅读。", sources: [] }],
  } });
  if (path.endsWith("/sessions/unknown-browser")) return json(response, { code: 0, data: {
    ...summary, id: "unknown-browser", turns: [turn({ ...message, references: [], blocks: [
      { id: "before", type: "markdown", content: "未知块之前的正文。" },
      { id: "hidden_id", type: "future_internal_type", payload: "secret_payload" },
      { id: "after", type: "markdown", content: "未知块之后的正文。" },
    ] })],
  } });
  if (path.endsWith("/sessions/unsafe-browser")) return json(response, { code: 0, data: {
    ...summary, id: "unsafe-browser", turns: [turn({ ...message, blocks: [
      { id: "safe", type: "markdown", content: '安全正文 [[cite:unsafe]]。\n\n<img src="x" onerror="window.__messageXss=1">' },
    ], references: [{ id: "unsafe", type: "dataset", title: "只有必填字段的来源", url: "javascript:window.__messageXss=1" }] })],
  } });
  if (path.endsWith(`/sessions/${sessionId}/run`) && request.method === "POST") {
    postCount++;
    for await (const _ of request) { /* Consume the actual Client request. */ }
    response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
    let seq = 0;
    const event = (name, data) => response.write(`id: ${seq++}\nevent: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
    response.on("close", () => { streamDisconnected = !completed; });
    event("run_start", { run_id: "run_browser" });
    event("message_start", { message: { ...message, status: "running", blocks: [], references: [] } });
    event("delta", { text: "不应重复显示的旧正文", reasoning: "核对资料", turn: 1 });
    event("block_start", { message_id: message.id, block: { ...message.blocks[0], content: "" } });
    const citationSplit = message.blocks[0].content.indexOf("paper_ref") + 4;
    event("block_delta", { message_id: message.id, block_id: message.blocks[0].id, delta: message.blocks[0].content.slice(0, citationSplit) });
    await new Promise((resolve) => { finishCitation = resolve; });
    event("block_delta", { message_id: message.id, block_id: message.blocks[0].id, delta: message.blocks[0].content.slice(citationSplit) });
    event("block_end", { message_id: message.id, block_id: message.blocks[0].id });
    event("block_start", { message_id: message.id, block: { ...message.blocks[1], content: "" } });
    const split = message.blocks[1].content.indexOf('\n```\n');
    event("block_delta", { message_id: message.id, block_id: message.blocks[1].id, delta: message.blocks[1].content.slice(0, split) });
    const heartbeat = setInterval(() => response.write(": keepalive\n\n"), 1000);
    try {
      await new Promise((resolve) => { finishStream = resolve; });
      event("block_delta", { message_id: message.id, block_id: message.blocks[1].id, delta: message.blocks[1].content.slice(split) });
      event("block_end", { message_id: message.id, block_id: message.blocks[1].id });
      // The model submits references after the body; arrival order differs from citation order.
      for (const reference of message.references) event("reference_upsert", { message_id: message.id, reference });
      event("message_end", { message });
      completed = true;
      event("result", { status: "done", stop_reason: "stop", final_text: "不应重复显示的旧正文", message,
        output: { sources: [{ title: "不应重复显示的旧来源" }] }, turns: 1, duration_ms: 7 });
      response.end();
    } finally { clearInterval(heartbeat); }
    return;
  }
  if (path.startsWith("/api/")) return json(response, { code: 0, data: {} });
  const upstream = httpRequest(new URL(request.url, nextOrigin), { method: request.method,
    headers: { ...request.headers, host: nextOrigin.host } }, (result) => {
    response.writeHead(result.statusCode, result.headers);
    result.pipe(response);
  });
  upstream.on("error", (error) => { response.writeHead(502); response.end(String(error)); });
  request.pipe(upstream);
}
const server = createServer((request, response) => { void mock(request, response).catch((error) => {
  failures.push(String(error));
  if (!response.headersSent) response.writeHead(500);
  response.end();
}); });
// Next dev waits for its HMR socket before hydration; forward upgrades as well.
server.on("upgrade", (request, socket, head) => {
  const upstream = httpRequest(new URL(request.url, nextOrigin), {
    headers: { ...request.headers, host: nextOrigin.host },
  });
  upstream.on("upgrade", (response, upstreamSocket, upstreamHead) => {
    socket.write(`HTTP/1.1 ${response.statusCode} ${response.statusMessage}\r\n${Object.entries(response.headers).map(([key, value]) => `${key}: ${value}`).join("\r\n")}\r\n\r\n`);
    if (head.length) upstreamSocket.write(head);
    if (upstreamHead.length) socket.write(upstreamHead);
    socket.pipe(upstreamSocket).pipe(socket);
    socket.on("error", () => upstreamSocket.destroy());
    upstreamSocket.on("error", () => socket.destroy());
  });
  upstream.on("error", () => socket.destroy());
  upstream.end();
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

const edge = spawn(process.env.EDGE_PATH ?? String.raw`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`, [
  "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--user-data-dir=${join(output, `edge-profile-${Date.now()}`)}`, "--remote-debugging-pipe", "about:blank",
], { windowsHide: true, stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"] });
edge.stderr.on("data", () => {});
const pending = new Map();
const decoder = new StringDecoder("utf8");
let buffer = "";
let commandId = 0;
edge.stdio[4].on("data", (chunk) => {
  buffer += decoder.write(chunk);
  let position;
  while ((position = buffer.indexOf("\0")) >= 0) {
    const raw = buffer.slice(0, position);
    buffer = buffer.slice(position + 1);
    if (!raw) continue;
    const packet = JSON.parse(raw);
    if (packet.id && pending.has(packet.id)) {
      pending.get(packet.id)(packet);
      pending.delete(packet.id);
    }
    if (packet.method === "Runtime.exceptionThrown") failures.push(packet.params.exceptionDetails.exception?.description ?? packet.params.exceptionDetails.text);
    if (packet.method === "Network.loadingFailed") console.log("Network failure:", packet.params);
    if (packet.method === "Runtime.consoleAPICalled" && packet.params.type === "error") console.log("Browser error:", packet.params.args.map((arg) => arg.value ?? arg.description));
  }
});
function cdp(method, params = {}, sessionId) {
  const id = ++commandId;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 60000);
    pending.set(id, (packet) => {
      clearTimeout(timeout);
      packet.error ? reject(new Error(packet.error.message)) : resolve(packet.result);
    });
    edge.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + "\0");
  });
}
let session;
async function evaluate(expression) {
  const result = await cdp("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, session);
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
  return result.result.value;
}
async function waitFor(expression, label) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try { if (await evaluate(`Boolean(${expression})`)) return; }
    catch (error) { if (!/context.*destroyed|context.*found|navigat/i.test(error.message)) throw error; }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`Timeout waiting for ${label}: ${JSON.stringify(failures)} ${(await evaluate("document.body?.innerText"))?.slice(-1800)}`);
}
async function screenshot(name) {
  const result = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false }, session);
  writeFileSync(join(output, name), Buffer.from(result.data, "base64"));
}
try {
  const { targetId } = await cdp("Target.createTarget", { url: "about:blank" });
  session = (await cdp("Target.attachToTarget", { targetId, flatten: true })).sessionId;
  await cdp("Page.enable", {}, session);
  await cdp("Runtime.enable", {}, session);
  await cdp("Network.enable", {}, session);
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1250, deviceScaleFactor: 1, mobile: false }, session);
  await cdp("Page.navigate", { url: `${origin}/agents?session=${sessionId}` }, session);
  await waitFor("document.querySelector('textarea') && !document.querySelector('textarea').disabled", "hydrated session");
  await evaluate(`(() => {const input=document.querySelector('textarea');input.focus();Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(input,'请展示结构化回复');input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await waitFor("document.querySelector('button[aria-label=发送]') && !document.querySelector('button[aria-label=发送]').disabled", "enabled send");
  await evaluate("document.querySelector('button[aria-label=发送]').click()");
  await waitFor("document.querySelector('article')?.innerText.includes('Transformer 首次提出')", "partial citation");
  assert.equal(await evaluate("document.querySelector('article').innerText.includes('[[cite:') || document.querySelector('article').innerText.includes('pape')"), false);
  assert.equal(await evaluate("document.querySelectorAll('article sup a').length"), 0);
  finishCitation();
  checks.push("split citation is withheld until complete, without exposing internal reference IDs");
  await waitFor("document.querySelector('article[aria-label=\"AI 回复\"] table') && document.querySelector('article .katex') && document.querySelector('article pre')", "streaming Markdown/table/math/code");
  assert.equal(await evaluate("document.querySelector('article [role=status]').textContent"), "生成中…");
  assert.equal(await evaluate("document.querySelectorAll('article sup span').length"), 1);
  assert.equal(await evaluate("document.querySelector('article sup span').textContent"), "1");
  assert.equal(await evaluate("document.querySelector('article section[aria-label=参考来源]') === null"), true);
  assert.equal(await evaluate("document.querySelector('article').innerText.includes('[[cite:')"), false);
  checks.push("live SSE renders Markdown, table, math, incomplete code and citation before message_end");
  await screenshot("message-streaming.png");
  finishStream();
  await waitFor("document.querySelector('article [role=status]')?.textContent === '已完成' && document.querySelectorAll('article sup a').length === 2", "terminal message");
  const text = await evaluate("document.querySelector('article').innerText");
  for (const hidden of ["internal_message_id", "internal_block_1", "internal_paper_entity", "schema_version", "internal_model_name", "paper_ref", "web_ref", "[[cite:"]) assert.equal(text.includes(hidden), false, hidden);
  assert.match(text, /参考来源（2）/);
  assert.equal(text.includes("不应展示的未引用来源"), false);
  assert.equal(await evaluate("document.querySelector('article li').innerText.includes('Attention Is All You Need')"), true);
  assert.match(text, /Vaswani et al\. · NeurIPS 2017/);
  assert.match(text, /huggingface\.co/);
  assert.match(text, /2026\/11\/26 08:00/);
  assert.equal(await evaluate("document.body.innerText.includes('不应重复显示')"), false);
  assert.equal(await evaluate("document.querySelectorAll('article[aria-label=\"AI 回复\"]').length"), 1);
  assert.equal(await evaluate("document.querySelectorAll('article a[target=_blank]:not([rel=\"noopener noreferrer\"])').length"), 0);
  await evaluate("document.querySelector('article sup a').click()");
  assert.equal(await evaluate("document.querySelector('article sup a').hash.slice(1) === document.querySelector('article li:target')?.id"), true);
  checks.push("metadata, source fields, internal-ID hiding, no duplicate legacy content and citation anchor navigation");
  await evaluate("document.querySelector('article').scrollIntoView({block:'start'})");
  await screenshot("message-desktop.png");
  const previousTimeOrigin = await evaluate("performance.timeOrigin");
  await cdp("Page.reload", {}, session);
  await waitFor(`performance.timeOrigin !== ${previousTimeOrigin} && document.querySelectorAll('article sup a').length === 2`, "historical snapshot after reload");
  assert.equal(postCount, 1);
  checks.push("reload restores the same structured message without rerunning Agent");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 1100, deviceScaleFactor: 1, mobile: true }, session);
  await waitFor("document.querySelector('article')", "mobile message");
  await evaluate("document.querySelector('article').scrollIntoView({block:'start'})");
  await new Promise((resolve) => setTimeout(resolve, 200));
  assert.equal(await evaluate("document.documentElement.scrollWidth <= innerWidth + 1 && document.querySelector('article').scrollWidth <= document.querySelector('article').clientWidth + 1"), true);
  await screenshot("message-mobile.png");
  checks.push("390px mobile layout without horizontal page overflow");
  for (const [id, visible] of [["legacy-browser", "旧会话仍可阅读"], ["unknown-browser", "暂不支持此内容的展示"], ["unsafe-browser", "只有必填字段的来源"]]) {
    await cdp("Page.navigate", { url: `${origin}/agents?session=${id}` }, session);
    await waitFor(`document.body?.innerText.includes(${JSON.stringify(visible)})`, id);
    if (id === "unknown-browser") {
      assert.equal(await evaluate("document.body.innerText.includes('未知块之前') && document.body.innerText.includes('未知块之后') && !document.body.innerText.includes('secret_payload') && !document.body.innerText.includes('future_internal_type')"), true);
    }
    if (id === "unsafe-browser") {
      assert.equal(await evaluate("document.querySelectorAll('article a[target=_blank]').length"), 0);
      assert.equal(await evaluate("window.__messageXss === undefined && document.querySelectorAll('article img').length === 0"), true);
    }
  }
  checks.push("legacy fallback, unknown block isolation and unsafe URL/HTML protection");
  assert.equal(streamDisconnected, false);
  assert.deepEqual(failures, []);
  const result = { checks, screenshots: ["message-streaming.png", "message-desktop.png", "message-mobile.png"], postCount, browserErrors: failures };
  writeFileSync(join(output, "result.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  if (session) await screenshot("failure.png").catch(() => {});
  if (session) writeFileSync(join(output, "failure.html"), await evaluate("document.querySelector('article')?.outerHTML ?? document.body.innerHTML").catch(() => ""));
  throw error;
} finally {
  finishCitation?.();
  finishStream?.();
  edge.kill();
  server.closeAllConnections();
  server.close();
}
