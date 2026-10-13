#!/usr/bin/env node
/**
 * CDP 截图工具 —— 等待页面出现指定文本后再截图(真实时间,非 virtual-time)
 *
 * 为什么需要它:--virtual-time-budget 会把虚拟时间快进完,客户端 effect
 * 还没来得及 flush 就截图了(拍到的永远是 SSR 首帧)。本脚本用 CDP 轮询
 * document.body.innerText,直到目标文本出现(或超时)再 Page.captureScreenshot。
 *
 * 运行方式(重要):必须由 **Windows 侧 node** 执行
 * (C:\Program Files\nodejs\node.exe)。
 * 传输用 --remote-debugging-pipe(fd3 写 / fd4 读,NUL 分隔):
 * 本机 loopback 上 WebSocket 连接会被莫名丢弃(实测 curl/netstat 均异常),
 * 管道不碰网络,最稳。
 * 脚本路径用 UNC:\\wsl.localhost\Ubuntu-24.04\home\hkr\projects\shenzhi\scripts\shot-cdp.mjs
 *
 * 用法:
 *   node.exe shot-cdp.mjs --url http://localhost:3100/agents/deep-research?mode=instant \
 *     --out "C:\Users\xxx\AppData\Local\Temp\f_dr_report.png" \
 *     --width 1440 --height 2400 --wait-text 参考文献 [--settle 500] [--timeout 45000]
 */
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";

const EDGE = String.raw`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`;

function parseArgs(argv) {
  const args = { width: 1440, height: 1500, settle: 500, timeout: 45000 };
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i]
      .replace(/^--/, "")
      .replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    args[key] = argv[i + 1];
  }
  for (const k of ["width", "height", "settle", "timeout"]) args[k] = Number(args[k]);
  if (!args.url || !args.out || !args.waitText) {
    console.error("missing --url / --out / --wait-text");
    process.exit(2);
  }
  return args;
}

const args = parseArgs(process.argv);
if (args.theme && !["light", "dark"].includes(args.theme)) {
  throw new Error("--theme must be light or dark");
}
// Optional browser-only responses for repeatable visual examples; no API or database changes.
const fixtures = args.responseFixture ? JSON.parse(readFileSync(args.responseFixture, "utf8")) : {};
const expectedUrl = new URL(args.url);
const profile = mkdtempSync(join(tmpdir(), "edge-cdp-"));

const edge = spawn(
  args.browser || EDGE,
  [
    "--headless",
    "--disable-gpu",
    "--no-first-run",
    `--user-data-dir=${profile}`,
    `--window-size=${args.width},${args.height}`,
    "--remote-debugging-pipe",
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"], windowsHide: true },
);
edge.on("error", (error) => { console.error(error.message); process.exit(1); });
const watchdog = setTimeout(() => {
  edge.kill();
  console.error("Browser/CDP timed out");
  process.exit(1);
}, args.timeout + 30000);

const toEdge = edge.stdio[3]; // 父进程写入 → Edge 的 fd3
const fromEdge = edge.stdio[4]; // Edge 的 fd4 → 父进程读取
edge.stderr.on("data", () => {}); // 吞掉噪音,避免缓冲满

let msgId = 0;
const pending = new Map();
let recvBuf = "";
fromEdge.on("data", (chunk) => {
  recvBuf += chunk.toString("utf8");
  let idx;
  while ((idx = recvBuf.indexOf("\0")) >= 0) {
    const raw = recvBuf.slice(0, idx);
    recvBuf = recvBuf.slice(idx + 1);
    if (!raw) continue;
    const msg = JSON.parse(raw);
    if (msg.method === "Fetch.requestPaused") {
      const { requestId, request } = msg.params;
      const url = new URL(request.url);
      const fixture = url.origin === expectedUrl.origin ? fixtures[url.pathname] : undefined;
      const response = fixture === undefined
        ? cdp("Fetch.continueRequest", { requestId }, msg.sessionId)
        : cdp("Fetch.fulfillRequest", {
          requestId, responseCode: 200,
          responseHeaders: [{ name: "Content-Type", value: "application/json" }],
          body: Buffer.from(JSON.stringify(fixture)).toString("base64"),
        }, msg.sessionId);
      response.catch((error) => { console.error(error.message); edge.kill(); process.exit(1); });
    }
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  }
});
function cdp(method, params = {}, sessionId) {
  const id = ++msgId;
  return new Promise((resolve, reject) => {
    pending.set(id, (msg) =>
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result),
    );
    toEdge.write(JSON.stringify({ id, method, params, sessionId }) + "\0");
  });
}

const { targetId } = await cdp("Target.createTarget", { url: "about:blank" });
const { sessionId } = await cdp("Target.attachToTarget", {
  targetId,
  flatten: true,
});
await cdp("Page.enable", {}, sessionId);
if (args.theme) {
  await cdp("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: args.theme }],
  }, sessionId);
  await cdp("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("shenzhi-theme", ${JSON.stringify(args.theme)}); } catch {}`,
  }, sessionId);
}
if (Object.keys(fixtures).length) {
  await cdp("Fetch.enable", { patterns: [{ urlPattern: `${expectedUrl.origin}/api/*` }] }, sessionId);
}
// headless 下 createTarget 不接受宽高,用设备指标覆盖设定视口
await cdp(
  "Emulation.setDeviceMetricsOverride",
  { width: args.width, height: args.height, deviceScaleFactor: 1, mobile: false },
  sessionId,
);
await cdp("Page.navigate", { url: args.url }, sessionId);

// 轮询目标文本(真实时间;页面定时器按真实节奏走)
const deadline = Date.now() + args.timeout;
let found = false;
while (Date.now() < deadline) {
  const { result } = await cdp(
    "Runtime.evaluate",
    {
      expression: `document.body ? document.body.innerText.includes(${JSON.stringify(args.waitText)}) : false`,
      returnByValue: true,
    },
    sessionId,
  );
  if (result.value) {
    found = true;
    break;
  }
  await new Promise((r) => setTimeout(r, 250));
}
if (!found)
  console.error(`等待文本「${args.waitText}」超时，此截图不能作为通过证据`);

await new Promise((r) => setTimeout(r, args.settle));

const { result: inspected } = await cdp("Runtime.evaluate", {
  expression: `(() => {
    const root = document.documentElement;
    const css = getComputedStyle(root);
    return {
      url: location.href,
      theme: root.classList.contains("dark") ? "dark" : "light",
      colors: Object.fromEntries(["background", "sidebar", "topbar", "card", "popover", "body", "primary", "primary-foreground", "selected", "selected-foreground", "ink", "faint"]
        .map(name => [name, css.getPropertyValue("--color-" + name).trim()]))
    };
  })()`, returnByValue: true,
}, sessionId);
const state = inspected.value;
const validPath = state && new URL(state.url).pathname === (args.expectedPath || expectedUrl.pathname);
const validTheme = !args.theme || state?.theme === args.theme;
const validPalette = !args.expectedPrimary || state?.colors.primary.toLowerCase() === args.expectedPrimary.toLowerCase();
const passed = found && validPath && validTheme && validPalette;
if (!validPath) console.error("截图页面路径与预期不一致");
if (!validTheme) console.error("实际主题与预期不一致");
if (!validPalette) console.error("实际主色与候选方案不一致");

const shot = await cdp(
  "Page.captureScreenshot",
  { format: "png", captureBeyondViewport: true },
  sessionId,
);
mkdirSync(dirname(args.out), { recursive: true });
writeFileSync(args.out, Buffer.from(shot.data, "base64"));
writeFileSync(`${args.out}.json`, JSON.stringify({
  ...state, passed, waitText: args.waitText,
  fixturePaths: Object.keys(fixtures), viewport: { width: args.width, height: args.height },
}, null, 2));

edge.kill();
clearTimeout(watchdog);
// 临时 profile 用完即删(Edge 释放句柄需稍作等待,失败不致命)
setTimeout(() => {
  try {
    rmSync(profile, { recursive: true, force: true, maxRetries: 3 });
  } catch {}
  console.log(`${args.out} written (${passed ? "ok" : "FAILED"})`);
  process.exit(passed ? 0 : 1);
}, 500);
