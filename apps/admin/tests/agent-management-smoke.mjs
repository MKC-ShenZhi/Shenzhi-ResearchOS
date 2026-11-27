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
  try {
    await waitFor(() => evaluate('document.body?.innerText.includes(' + JSON.stringify(text) + ')'), 'Missing UI text: ' + text);
  } catch (error) {
    throw new Error(error.message + '\n' + await evaluate('document.body?.innerText.slice(-4000)'));
  }
}
async function navigate(hash, heading, expected) {
  await evaluate('location.hash = ' + JSON.stringify(hash));
  await waitFor(() => evaluate('document.querySelector("main h2")?.textContent === ' + JSON.stringify(heading)),
    'Route heading missing: ' + hash);
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
  await see('深知 · Agent 管理');
  await see('供应商与模型目录');
  await waitFor(() => evaluate(`(() => {
    const model = [...document.querySelectorAll('.agent-model-title small')].find(node => node.textContent === 'deepseek/deepseek-chat');
    const group = model?.closest('.agent-provider-group');
    return !!group?.querySelector('a[href="#/agent/providers/deepseek"]') &&
      ['API 地址', '凭据状态', 'deepseek/deepseek-chat'].every(label => group.textContent.includes(label));
  })()`), 'DeepSeek model must appear inside its provider group');
  await evaluate(`(() => {
    const search = document.querySelector('input[type=search]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, 'deepseek/deepseek-chat');
    search.dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  await waitFor(() => evaluate(`document.querySelectorAll('.agent-provider-group').length === 1 &&
    document.querySelectorAll('.agent-provider-group li').length === 1 &&
    document.querySelector('.agent-provider-group').innerText.includes('deepseek/deepseek-chat')`),
  'Model search must keep its provider group');
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('nav[aria-label="Agent 管理"] a')]
    .map(link => [link.getAttribute('href'), link.querySelector('strong').textContent])`), [
    ['#/agent/providers', '模型与供应商'], ['#/agent/tools', 'Tools'], ['#/agent/skills', 'Skills'],
  ]);
  assert.equal(await evaluate("document.querySelector('.agent-provider-group').open"), true);
  const address = await evaluate(`(() => {
    const group = document.querySelector('.agent-provider-group');
    const row = [...group.querySelectorAll('.agent-fields > div')].find(row => row.querySelector('dt button')?.textContent === 'API 地址');
    const link = row.querySelector('dd a');
    const help = [...group.querySelectorAll('.agent-field-label')].find(button => button.textContent === '凭据状态');
    help.focus();
    return { href: link?.getAttribute('href'), target: link?.target,
      tooltip: getComputedStyle(help.parentElement.querySelector('[role=tooltip]')).display,
      description: help.parentElement.querySelector('[role=tooltip]').textContent };
  })()`);
  assert.match(address.href, /^https?:/);
  assert.equal(address.target, '_blank');
  assert.equal(address.tooltip, 'block');
  assert(address.description.includes('非空 API Key'));
  await evaluate("document.querySelector('.agent-model-trigger').click()");
  await see('最大输出 Token');
  await see('停止使用');
  assert.equal(await evaluate("document.querySelector('.agent-model-drawer').open"), true);
  await evaluate("document.querySelector('.agent-drawer-heading button').click()");
  assert.equal(await evaluate("document.querySelector('.agent-model-drawer').open"), false);
  await evaluate("document.querySelector('.agent-provider-group summary').click()");
  assert.equal(await evaluate("document.querySelector('.agent-provider-group').open"), false);
  await navigate('#/agent/providers/deepseek', 'Provider 详情', '关联模型');
  await navigate('#/agent/models/deepseek%2Fdeepseek-chat', 'Model 详情', '上游 Model ID');
  await see('上下文长度');
  await see('最大输出 Token');
  await see('停止使用');
  assert.equal(await evaluate('document.querySelector(".agent-modules [aria-current]").hash'), '#/agent/providers');
  await navigate('#/agent/tools', 'Tools', 'tool:web_search');
  await navigate('#/agent/tools/tool%3Aweb_search', 'Tools 详情', '参数 Schema');
  await navigate('#/agent/skills', 'Skills', 'deep-research');
  await navigate('#/agent/skills/deep-research', 'Skills 详情', '资源文件');
  await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent.includes('预览 SKILL.md')).click()");
  await waitFor(() => evaluate('document.querySelector("pre.agent-preview")?.textContent.length > 20'), 'Skill preview missing');
  for (const removed of ['overview', 'tasks/task0', 'runs/run0', 'workers/worker-a', 'alerts', 'audit', 'config/fleet']) {
    await navigate('#/agent/' + removed, '供应商与模型目录', 'deepseek');
  }
  await navigate('#/capabilities', '供应商与模型目录', 'deepseek');
  await navigate('#/agent/models', '供应商与模型目录', 'deepseek');
  if (phase === '--phase2') {
    await navigate('#/agent/config', 'Provider / Model 配置', '创建初始候选');
    await see('配置写入关闭');
    await evaluate("document.querySelector('.agent-management summary').click()");
    const editor = await evaluate(`(() => {
      const form = document.querySelector('.agent-candidate');
      return { addProvider: [...form.querySelectorAll('button')].find(b => b.textContent === '新增 Provider')?.matches(':disabled'),
        addModel: [...form.querySelectorAll('button')].find(b => b.textContent === '新增 Model')?.matches(':disabled'),
        importDisabled: form.querySelector('input[type=file]').disabled,
        previewDisabled: [...form.querySelectorAll('button')].find(b => b.textContent === '检查依赖并预览')?.disabled };
    })()`);
    assert.deepEqual(editor, { addProvider: true, addModel: true, importDisabled: true, previewDisabled: true });
  }
  assert.deepEqual(exceptions, []);
  const api = requests.filter(request => request.url.includes('/api/'));
  assert(api.every(request => request.url.startsWith(origin + '/api/v1/admin-console/')));
  assert(api.every(request => !Object.keys(request.headers).some(key => key.toLowerCase() === 'authorization')));
  const managed = api.filter(request => request.url.includes('/admin-console/agent/'));
  assert(managed.some(request => new URL(request.url).pathname.endsWith('/skills/deep-research/document')));
  assert(managed.every(request => request.method === 'GET' &&
    /\/agent\/(providers|models|tools|skills|model-metadata)(\/|$)|\/agent\/config\/revisions$/.test(new URL(request.url).pathname)));
  console.log('Admin Agent management browser smoke passed');
} finally {
  socket?.close();
  browser.kill();
  await new Promise(resolve => { if (browser.exitCode !== null || browser.signalCode) resolve(); else browser.once('exit', resolve); });
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(() => {});
}
