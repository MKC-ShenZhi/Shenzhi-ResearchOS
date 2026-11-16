#!/usr/bin/env node
/**
 * CDP 截图工具 —— 等待页面出现指定文本后再截图(真实时间,非 virtual-time)
 *
 * 为什么需要它:--virtual-time-budget 会把虚拟时间快进完,客户端 effect
 * 还没来得及 flush 就截图了(拍到的永远是 SSR 首帧)。本脚本用 CDP 轮询
 * document.body.innerText,直到目标文本出现(或超时)再 Page.captureScreenshot。
 *
 * 运行方式:Edge 路径默认按平台取,可用 EDGE_PATH 覆盖。
 * 传输用 --remote-debugging-pipe(fd3 写 / fd4 读,NUL 分隔),不依赖 loopback 网络。
 * 在 WSL 中开发时,需用 Windows 侧 node 执行本脚本(WSL 与 Windows 间的
 * loopback WebSocket 连接不稳定),脚本路径用 \\wsl.localhost\<发行版>\... 的 UNC 形式。
 *
 * 用法:
 *   node shot-cdp.mjs --url http://localhost:3100/agents/deep-research?mode=instant \
 *     --out /tmp/f_dr_report.png \
 *     --width 1440 --height 2400 --wait-text 参考文献 [--settle 500] [--timeout 45000]
 */
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";

const DEFAULT_EDGE = {
  win32: String.raw`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`,
  darwin: "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
}[process.platform] ?? "microsoft-edge";
const EDGE = process.env.EDGE_PATH || DEFAULT_EDGE;

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
const profile = mkdtempSync(join(tmpdir(), "edge-cdp-"));

const edge = spawn(
  EDGE,
  [
    "--headless",
    "--disable-gpu",
    "--no-first-run",
    `--user-data-dir=${profile}`,
    `--window-size=${args.width},${args.height}`,
    "--remote-debugging-pipe",
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"] },
);

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

const { targetId } = await cdp("Target.createTarget", { url: args.url });
const { sessionId } = await cdp("Target.attachToTarget", {
  targetId,
  flatten: true,
});
await cdp("Page.enable", {}, sessionId);
// headless 下 createTarget 不接受宽高,用设备指标覆盖设定视口
await cdp(
  "Emulation.setDeviceMetricsOverride",
  { width: args.width, height: args.height, deviceScaleFactor: 1, mobile: false },
  sessionId,
);

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
  console.error(`WARN: 等待文本「${args.waitText}」超时,按当前状态截图`);

await new Promise((r) => setTimeout(r, args.settle));

const shot = await cdp(
  "Page.captureScreenshot",
  { format: "png", captureBeyondViewport: true },
  sessionId,
);
mkdirSync(dirname(args.out), { recursive: true });
writeFileSync(args.out, Buffer.from(shot.data, "base64"));

edge.kill();
// 临时 profile 用完即删(Edge 释放句柄需稍作等待,失败不致命)
setTimeout(() => {
  try {
    rmSync(profile, { recursive: true, force: true, maxRetries: 3 });
  } catch {}
  console.log(`${args.out} written (${found ? "ok" : "TIMEOUT"})`);
  process.exit(0);
}, 500);
