import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../../api';
import { useResource } from '../../useResource';

type Kind = 'provider' | 'model' | 'tool' | 'skill' | 'task' | 'run' | 'worker';
type Capability = { kind: string; id: string; version: string | null; scope: string; conditions: string[] };
type Worker = {
  worker_id: string; instance_id: string; state: string; observed_at: string; started_at: string;
  expires_at: string; age_seconds: number; health: string; active_run_id: string | null; run_tool_ids: string[];
  manifest_digest: string | null; capability_count: number;
  manifest: { runtime_version: string; build_revision: string | null; config_revision: string | null;
    registry_digest: string | null; capabilities: Capability[] } | null;
};
type Check = {
  state: string; reason: string; profile: string; observed_at: string; expires_at: string;
  duration_ms: number; budget_tokens: number; source: string; instance_id: string; build_revision: string | null;
  config_revision: string | null; capability_version: string | null;
  steps: { name: string; state: string; reason: string | null }[];
};
type Diagnostic = {
  source: string; reason: string; observed_at: string; occurred_at: string | null; worker_id: string | null;
  build_revision: string | null; config_revision: string | null; call_id: string | null; run_id: string | null;
};
type Audit = { audit_id: string; request_id: string; principal: string; action: string; target_kind: Kind;
  target_id: string; created_at: string; state: string; reason: string | null; source: string; check: Check | null };
type Page<T> = { items: T[]; next_cursor: string | null };

const root = '/agent';
const stamp = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '未知';
const idPath = (value: string) => encodeURIComponent(value);
const labels: Record<string, string> = {
  online: '在线', stale: '陈旧', offline: '离线', ok: '正常', degraded: '异常',
  pass: '通过', fail: '失败', pending: '检查中', unknown: '未知', unsupported: '不支持',
};
const suggestions: Record<string, string> = {
  WORKER_OFFLINE: '核对 Worker 进程、凭据和 Agent API 连通性。',
  WORKER_STALE: '核对最近一次上报、服务负载和网络。',
  LEASE_EXPIRED: '对照最后执行节点和 Execution 历史排查租约超时。',
  authorization_denied: '核对已绑定的 Policy 和实际能力版本。',
  MODEL_CALL_FAILED: '对照 Provider 凭据状态及独立模型检查。',
  TOOL_CALL_FAILED: '先检查工具依赖及环境，避免复跑带副作用的工具。',
  SKILL_METADATA_OR_RESOURCE_INVALID: '核对固定版本的 Frontmatter 及受控资源路径。',
};
function write<T>(path: string, data: object = {}) {
  return api<T>(root + path, { method: 'POST', body: JSON.stringify(data) });
}

function ManifestHistory({ workerId }: { workerId: string }) {
  const [cursor, setCursor] = useState('');
  const resource = useResource<Page<{ digest: string; last_seen: string; config_revision: string | null;
    build_revision: string | null; capability_count: number }>>(root + '/worker-evidence/' +
      idPath(workerId) + '/manifests' + (cursor ? '?cursor=' + idPath(cursor) : ''));
  return <details><summary>Manifest 历史</summary>
    {resource.error && <p role="alert">{resource.error}</p>}
    {resource.loading && <p role="status">正在读取…</p>}
    {resource.data?.items.map(item => <p key={item.digest}>{stamp(item.last_seen)} · {item.config_revision ?? '未知'}
      {' · '}{item.build_revision ?? '未知'} · {item.capability_count} 项 · {item.digest}</p>)}
    {resource.data?.next_cursor && <button onClick={() => setCursor(resource.data?.next_cursor ?? '')}>下一页</button>}</details>;
}


function WorkerDistribution({ kind, id }: { kind: Kind; id: string }) {
  const [cursor, setCursor] = useState('');
  const source = useResource<Page<{ worker_id: string; state: string; observed_at: string;
    config_revision: string | null; capability: Capability | null }>>(root + '/capability-evidence?kind=' +
      kind + '&target_id=' + idPath(id) + (cursor ? '&cursor=' + idPath(cursor) : ''));
  return <details><summary>Worker 能力分布</summary>
    {source.error && <p role="alert">{source.error}</p>}
    {source.loading && <p role="status">正在读取…</p>}
    {source.data && !source.data.items.length && <p>暂无 Worker 清单证据</p>}
    {source.data?.items.map(item => <p key={item.worker_id}>
      <a href={'#/agent/workers/' + idPath(item.worker_id)}>{item.worker_id}</a>
      {' · '}{labels[item.state]} · {stamp(item.observed_at)} · Config {item.config_revision ?? '未知'}
      {' · '}{item.capability ? item.capability.scope + ' / ' + (item.capability.version ?? '未知') : '清单未观测'}
    </p>)}
    {source.data?.next_cursor && <button onClick={() => setCursor(source.data?.next_cursor ?? '')}>下一页</button>}</details>;
}


function WorkerFields({ worker }: { worker: Worker }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);
  return <dl className="agent-fields">
    <div><dt>状态</dt><dd>{worker.state === 'online' && now >= Date.parse(worker.expires_at) ? '陈旧 · 需刷新' : labels[worker.state]}</dd></div>
    <div><dt>心跳时间</dt><dd>{stamp(worker.observed_at)}</dd></div>
    <div><dt>距心跳</dt><dd>{Math.max(worker.age_seconds, Math.floor((now - Date.parse(worker.observed_at)) / 1000))} 秒</dd></div>
    <div><dt>启动时间</dt><dd>{stamp(worker.started_at)}</dd></div>
    <div><dt>实例 ID</dt><dd>{worker.instance_id}</dd></div>
    <div><dt>上报健康</dt><dd>{labels[worker.health]}</dd></div>
    <div><dt>能力数量</dt><dd>{worker.capability_count}</dd></div>
    <div><dt>当前 Run</dt><dd>{worker.active_run_id
      ? <a href={'#/agent/runs/' + idPath(worker.active_run_id)}>{worker.active_run_id}</a> : '无上报'}</dd></div>
    <div><dt>当前 Run 已启用工具</dt><dd>{worker.run_tool_ids.join('、') || '无上报'}</dd></div>
    <div><dt>Manifest</dt><dd>{worker.manifest_digest ?? '未知'}</dd></div>
  </dl>;
}

export function WorkerEvidence({ workerId }: { workerId?: string }) {
  const [lookup, setLookup] = useState('');
  const [cursor, setCursor] = useState('');
  const suffix = workerId ? '/' + idPath(workerId) : cursor ? '?cursor=' + idPath(cursor) : '';
  const query = useResource<Worker | Page<Worker>>(root + '/worker-evidence' + suffix);
  useEffect(() => {
    const timer = window.setInterval(query.refresh, 30_000);
    return () => window.clearInterval(timer);
    // Refresh belongs to the current resource path.
  }, [suffix]);
  const [comparisonId, setComparisonId] = useState('');
  const [comparison, setComparison] = useState<Worker>();
  const [compareError, setCompareError] = useState('');
  if (!workerId) {
    const data = query.data as Page<Worker> | undefined;
    return <article><h2>Worker 心跳</h2><form className="agent-filters" onSubmit={event => {
      event.preventDefault();
      if (lookup.trim()) location.hash = '#/agent/workers/' + idPath(lookup.trim());
    }}><label>Worker ID<input value={lookup} maxLength={255} onChange={event => setLookup(event.target.value)} /></label><button>查看</button></form>
      {query.loading && <p role="status">正在读取心跳…</p>}
      {query.error && <p role="alert">{query.error}</p>}
      {data && !data.items.length && <p>暂无心跳证据</p>}
      {data?.items.map(item => <details key={item.worker_id}><summary>
        <a href={'#/agent/workers/' + idPath(item.worker_id)}>{item.worker_id}</a> · {labels[item.state]} · {stamp(item.observed_at)}
      </summary><WorkerFields worker={item} /></details>)}
      <div className="actions"><button onClick={query.refresh}>刷新</button>
        {cursor && <button onClick={() => setCursor('')}>第一页</button>}
        {data?.next_cursor && <button onClick={() => setCursor(data.next_cursor ?? '')}>下一页</button>}</div>
    </article>;
  }
  const worker = query.data as Worker | undefined;
  const actual = worker?.manifest?.capabilities ?? [];
  const other = comparison?.manifest?.capabilities ?? [];
  const mismatches = comparison ? [...new Set([...actual, ...other].map(item => item.kind + ':' + item.id))]
    .filter(key => {
      const match = (item: Capability) => item.kind + ':' + item.id === key;
      return JSON.stringify(actual.find(match)) !== JSON.stringify(other.find(match));
    }) : [];
  async function compare(event: FormEvent) {
    event.preventDefault(); setCompareError(''); setComparison(undefined);
    try { setComparison(await api<Worker>(root + '/worker-evidence/' + idPath(comparisonId.trim()))); }
    catch (error) { setCompareError((error as Error).message); }
  }
  return <article><h2>Worker 心跳与 Manifest</h2><button onClick={query.refresh}>刷新心跳</button>
    {query.loading && <p role="status">正在读取心跳…</p>}
    {query.error && <p role="alert">{query.error}。可参阅下方租约证据。</p>}
    {worker && <><WorkerFields worker={worker} />
      <p>Build {worker.manifest?.build_revision ?? '未知'} · Config {worker.manifest?.config_revision ?? '未知'} · Runtime {worker.manifest?.runtime_version ?? '未知'}</p>
      <p>Registry {worker.manifest?.registry_digest ?? '未知'}</p>
      <details><summary>能力证据</summary>
        <div className="table-wrap"><table><thead><tr><th>能力</th><th>版本</th><th>范围</th><th>条件</th></tr></thead><tbody>
          {actual.map(item => <tr key={item.kind + item.id}><td>{item.kind} · {item.id}</td><td>{item.version ?? '未知'}</td>
            <td>{item.scope}</td><td>{item.conditions.join('、') || '—'}</td></tr>)}
        </tbody></table></div>
      </details>
      <ManifestHistory workerId={workerId} />
      <form className="agent-filters" onSubmit={compare}>
        <label>对照 Worker ID<input required value={comparisonId} maxLength={255} onChange={event => setComparisonId(event.target.value)} /></label><button>比较</button>
      </form>
      {compareError && <p role="alert">{compareError}</p>}
      {comparison && <p>与 {comparison.worker_id} 对比：{worker.manifest && comparison.manifest
        ? mismatches.join('、') || '已上报能力相同' : 'Manifest 不完整'}</p>}
    </>}
    <Diagnosis kind="worker" id={workerId} />
  </article>;
}

function CheckView({ check }: { check: Check }) {
  const [time, setTime] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setTime(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);
  return <div>
    <p>{time >= Date.parse(check.expires_at) ? '已过期' : labels[check.state]} · {check.reason} · {check.duration_ms} ms · {stamp(check.observed_at)}</p>
    <p>来源 {check.source} / {check.instance_id} · Build {check.build_revision ?? '未知'} · Config {check.config_revision ?? '未知'} · 能力版本 {check.capability_version ?? '未知'} · 预算 {check.budget_tokens} Token</p>
    {check.steps.length > 0 && <ul>{check.steps.map(step => <li key={step.name}>{step.name} · {labels[step.state]} {step.reason}</li>)}</ul>}
  </div>;
}

export function LatestHealth({ kind, id }: { kind: 'provider' | 'model' | 'tool' | 'skill'; id: string }) {
  const history = useResource<Page<Audit>>(root + '/audit?action=check&limit=1&target_kind=' + kind + '&target_id=' + idPath(id));
  const [time, setTime] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setTime(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);
  if (history.loading) return <span>读取中…</span>;
  if (history.error) return <span title={history.error}>检查记录不可用</span>;
  const entry = history.data?.items[0];
  if (!entry) return <span>暂无检查</span>;
  const check = entry.check;
  const expired = check && time >= Date.parse(check.expires_at);
  return <span title={entry.reason ?? undefined}>
    {expired ? '已过期' : labels[check?.state ?? entry.state] ?? '未知'}
    {check && <> · {check.profile}</>}<br />{stamp(check?.observed_at ?? entry.created_at)}
  </span>;
}

export function HealthChecks({ kind, id }: { kind: 'provider' | 'model' | 'tool' | 'skill'; id: string }) {
  const [profile, setProfile] = useState('static');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Audit>();
  const history = useResource<Page<Audit>>(root + '/audit?action=check&limit=10&target_kind=' + kind + '&target_id=' + idPath(id));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true); setResult(undefined); setError('');
    try { setResult(await write<Audit>('/checks', { operation_id: crypto.randomUUID(), kind, target_id: id, profile })); }
    catch (failure) { setError((failure as Error).message); }
    finally { setPending(false); history.refresh(); }
  }
  return <article><h2>健康检查</h2>
    <form className="agent-filters" onSubmit={submit}>
      <label>检查类型<select value={profile} disabled={pending} onChange={event => setProfile(event.target.value)}>
        <option value="static">静态校验</option>
        {(kind === 'provider' || kind === 'model') && <option value="network">连通与认证</option>}
        {kind === 'model' && <><option value="completion">最小模型调用</option>
          <option value="streaming">Streaming</option><option value="tool_calling">Tool Calling</option></>}
      </select></label><button disabled={pending}>{pending ? '检查中…' : '发起检查'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result?.check ? <CheckView check={result.check} /> : result && <p>{labels[result.state]} · {result.reason}</p>}
    {(kind === 'tool' || kind === 'skill') && <p>安全检查只验证登记、可检查依赖与资源证据。</p>}
    <h3>最近检查</h3>
    {history.error && <p role="alert">{history.error}</p>}
    {history.data && !history.data.items.length && <p>未知 · 暂无检查记录</p>}
    {history.data?.items.map(item => <details key={item.audit_id}><summary>{stamp(item.created_at)} · {labels[item.state]} · {item.check?.profile ?? item.reason}</summary>
      <a href={'#/agent/audit/' + item.audit_id}>审计记录</a>{item.check && <CheckView check={item.check} />}</details>)}
    <WorkerDistribution kind={kind} id={id} />
    <Diagnosis kind={kind} id={id} />
  </article>;
}

export function Diagnosis({ kind, id }: { kind: Kind; id: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<Diagnostic>();
  async function inspect() {
    setBusy(true); setError('');
    try {
      const entry = await write<Audit>('/diagnostics', { operation_id: crypto.randomUUID(), kind, target_id: id });
      if (entry.state !== 'pass') throw new Error(entry.reason ?? '诊断证据不可用');
      setData(await write<Diagnostic>('/diagnostics/' + entry.audit_id + '/view'));
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return <section><h3>受控诊断</h3><button disabled={busy} onClick={() => void inspect()}>{busy ? '诊断中…' : '查看诊断'}</button>
    {error && <p role="alert">{error}</p>}
    {data && <div><p>{data.reason} · {data.source} · {stamp(data.occurred_at ?? data.observed_at)}</p>
      <p>Worker {data.worker_id ?? '未知'} · Build {data.build_revision ?? '未知'} · Config {data.config_revision ?? '未知'}</p>
      <p>Run {data.run_id ?? '未知'} · Call {data.call_id ?? '未知'}</p>
      <p>{suggestions[data.reason] ?? '对照目标的最新状态、能力版本和关联执行记录。'}</p></div>}
  </section>;
}

export function AgentAudit({ id }: { id?: string }) {
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState('');
  const [diagnostic, setDiagnostic] = useState<Diagnostic>();
  const [error, setError] = useState('');
  const resource = useResource<Audit | Page<Audit>>(root + '/audit' + (id
    ? '/' + idPath(id) : '?' + query + (offset ? '&offset=' + idPath(offset) : '')));
  const data = resource.data;
  const page = !id ? data as Page<Audit> | undefined : undefined;
  const items = id && data ? [data as Audit] : page?.items;
  return <><h1>Agent 管理审计</h1>
    {!id && <form className="agent-filters" onSubmit={event => {
      event.preventDefault();
      const filters = new URLSearchParams();
      new FormData(event.currentTarget).forEach((value, key) => {
        if (typeof value === 'string' && value.trim()) filters.set(key, /_at$/.test(key) ? new Date(value).toISOString() : value.trim());
      });
      setQuery(filters.toString()); setOffset('');
    }}>
      {([['principal', '操作者'], ['action', '操作'], ['target_kind', '目标类型'], ['target_id', '目标 ID'], ['state', '结果']] as const)
        .map(([key, label]) => <label key={key}>{label}<input name={key} maxLength={255} /></label>)}
      <label>起始时间<input type="datetime-local" name="from_at" /></label>
      <label>结束时间<input type="datetime-local" name="to_at" /></label><button>筛选</button>
    </form>}
    <button onClick={resource.refresh}>刷新</button>
    {resource.loading && <p role="status">正在读取…</p>}
    {(error || resource.error) && <p role="alert">{error || resource.error}</p>}
    {items?.length === 0 && <p>暂无记录</p>}
    {items?.map(item => <article key={item.audit_id}><p><a href={'#/agent/audit/' + item.audit_id}>{item.audit_id}</a> · {stamp(item.created_at)}</p>
      <p>{item.principal} · {item.action} · {item.target_kind}/{item.target_id} · {labels[item.state]} {item.reason}</p>
      {item.check && <CheckView check={item.check} />}
      {id && item.action === 'diagnose' && !diagnostic && <button onClick={async () => {
        setError('');
        try { setDiagnostic(await write<Diagnostic>('/diagnostics/' + item.audit_id + '/view')); }
        catch (failure) { setError((failure as Error).message); }
      }}>读取受控诊断</button>}
      {diagnostic && <p>{diagnostic.reason} · {diagnostic.source} · {stamp(diagnostic.observed_at)} · Worker {diagnostic.worker_id ?? '未知'}</p>}
    </article>)}
    <div className="actions">{offset && <button onClick={() => setOffset('')}>第一页</button>}
      {page?.next_cursor && <button onClick={() => setOffset(page.next_cursor ?? '')}>下一页</button>}</div>
  </>;
}
