// Runs against the isolated management integration server over Chrome DevTools.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const [chrome, origin, phase] = process.argv.slice(2);
assert(chrome && origin);
const profile = await mkdtemp(join(tmpdir(), 'shenzhi-admin-test-'));
const browser = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--disable-background-networking',
  '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'],
{ windowsHide: true, stdio: 'ignore' });
let socket;
let nextId = 0;
const pending = new Map();
const requests = [];
const exceptions = [];

async function waitFor(check, message) {
  const deadline = Date.now() + 12_000;
  while (Date.now() < deadline) {
    const result = await check();
    if (result) return result;
    await delay(100);
  }
  throw new Error(message);
}
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, message => message.error ? reject(new Error(message.error.message)) : resolve(message.result));
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
  return result.result.value;
}
async function see(text) {
  await waitFor(() => evaluate('document.body?.innerText.includes(' + JSON.stringify(text) + ')'), 'Missing UI text: ' + text);
}
async function navigate(hash, expected) {
  await evaluate('location.hash = ' + JSON.stringify(hash));
  await see(expected);
}

try {
  const port = await waitFor(async () => {
    try { return (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split(/\r?\n/)[0]; }
    catch { return null; }
  }, 'Chrome DevTools port unavailable');
  const [tab] = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
  socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data);
    if (pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
    if (message.method === 'Network.requestWillBeSent') requests.push(message.params.request);
    if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text);
  });
  await send('Network.enable');
  await send('Runtime.enable');
  await send('Page.navigate', { url: origin + '/#/agent' });
  await see('登录控制台');
  await evaluate(`document.querySelector('[name=username]').value = 'test-admin';
    document.querySelector('[name=password]').value = 'test-password';
    document.querySelector('form').requestSubmit();`);
  await see('Backend 权益 PostgreSQL');
  await navigate('#/agent/providers', 'deepseek');
  await navigate('#/agent/providers/deepseek', '关联模型');
  await navigate('#/agent/models/deepseek%2Fdeepseek-chat', '状态与证据');
  await see('上游 Model ID');
  await navigate('#/agent/tools', 'tool:web_search');
  await navigate('#/agent/tools/tool%3Aweb_search', '参数 Schema');
  await see('call0');
  await navigate('#/agent/skills', 'deep-research');
  await navigate('#/agent/skills/deep-research', 'References 与 Scripts');
  await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent.includes('预览 SKILL.md')).click()");
  await waitFor(() => evaluate('document.querySelector("pre.agent-preview")?.textContent.length > 20'), 'Skill preview missing');
  await navigate('#/agent/tasks', 'task0');
  await navigate('#/agent/tasks/task0', 'Backend 核验与入账');
  await see('run0');
  await navigate('#/agent/runs/run0', 'Execution 历史');
  await see('call0');
  await see('tool_started');
  await navigate('#/agent/workers/worker-a', '最近已记录活动');
  if (phase === '--phase2') {
    await see('phase2-browser-config');
    await navigate('#/agent/providers/deepseek', '发起检查');
    await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent === '发起检查').click()");
    await see('CHECK_PASSED');
    await navigate('#/agent/providers', '最近检查');
    await see('通过 · static');
    await navigate('#/agent/runs/run0', '查看诊断');
    await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent === '查看诊断').click()");
    await see('NO_FAILURE_EVIDENCE');
    await navigate('#/agent/audit', 'Agent 管理审计');
    await see('diagnostic_view');
    await navigate('#/agent/config', 'Agent 配置管理');
    await see('配置修订');
    await see('创建初始候选');
  }
  assert.deepEqual(exceptions, []);
  const api = requests.filter(request => request.url.includes('/api/'));
  assert(api.some(request => request.url.includes('/agent/runs/run0/calls')));
  assert(api.every(request => request.url.startsWith(origin + '/api/v1/admin-console/')));
  assert(api.every(request => !Object.keys(request.headers).some(key => key.toLowerCase() === 'authorization')));
  const managedWrites = api.filter(request => request.url.includes('/admin-console/agent/') && request.method !== 'GET');
  assert.equal(managedWrites.length, phase === '--phase2' ? 3 : 0);
  assert(managedWrites.every(request => request.method === 'POST' &&
    Object.entries(request.headers).some(([key, value]) => key.toLowerCase() === 'x-admin-request' && value === '1')));
  console.log('Admin Phase 1 browser smoke passed');
} finally {
  socket?.close();
  browser.kill();
  await new Promise(resolve => { if (browser.exitCode !== null || browser.signalCode) resolve(); else browser.once('exit', resolve); });
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(() => {});
}
