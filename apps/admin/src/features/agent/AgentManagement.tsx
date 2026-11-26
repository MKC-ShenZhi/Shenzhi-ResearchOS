import { useEffect, useState, type ReactNode } from 'react';
import { useResource } from '../../useResource';
import './agent.css';
import { AgentAudit, Diagnosis, HealthChecks, WorkerEvidence } from './AgentDiagnostics';
import { AgentAlerts, AgentControl } from './AgentOperations';
import { AgentConfigCenter } from './AgentConfigCenter';
import { AgentHealthSummary, CurrentHealth } from './AgentHealthSummary';
import { AgentOperationsOverview } from './AgentOperationsOverview';

type State = 'yes' | 'no' | 'unknown' | 'not_applicable';
type Evidence = { state: State; source: string | null; observed_at: string | null; config_revision?: string; worker_id?: string };
type States = Record<string, Evidence>;
type Snapshot = { status: string; observed_at: string; source: string; reason_code: string | null };
type Page<T> = { items: T[]; next_cursor: string | null; observed_at: string };
type Run = {
  run_id: string; task_id: string; attempt: number; status: string; worker_id: string | null;
  created_at: string; started_at: string | null; completed_at: string | null; duration_ms: number | null;
  lease_status: string; error_code: string | null;
  execution: { execution_id: string; worker_id: string; sealed: boolean } | null;
  executions: { execution_id: string; worker_id: string; sealed: boolean }[];
  executions_truncated: boolean;
};
type Worker = { worker_id: string; latest_run: Run; last_activity: string; active_executions: number; expired_leases: number; state: string };
type Usage = { status: string; measured_tokens: number | null; known_tokens: number | null; accounted_tokens: number | null; held_tokens: number | null; settlement_status: string | null };
type Task = {
  task_id: string; owner_id: string; mode: string | null; requested_model: string | null; status: string;
  created_at: string; latest_run: Run | null; error_code: string | null; observed_usage: Usage | null; backend_usage: Usage | null;
  execution_config_revision?: string | null; execution_wait_reason?: string | null;
};
type Call = {
  failure_reason?: string | null;
  call_id: string; execution_id: string; run_id: string; kind: string; capability_id: string | null;
  capability_version: string | null; status: string; started_at: string | null; duration_ms: number | null;
  usage_status: string; known_tokens: number | null;
};
type CatalogEntry = {
  provider_id?: string; model_id?: string; tool_id?: string; name?: string; label?: string; brand?: string;
  protocol?: string; base_url?: string; credential_present?: boolean; enabled?: boolean; model_ids?: string[];
  upstream_model_id?: string; capabilities?: Record<string, boolean | number | string | null>; default_purposes?: string[];
  config_revision?: string | null; capability_version?: string | null; schema_digest?: string | null;
  latest_observation?: { model_id: string; capability_version: string; observed_at: string; outcome: string; source: string } | null;
  parameters_schema?: object | null; conditions?: string[]; registration?: string; latent?: State; run_callable?: State;
  description?: string; source?: string; states: States; latest_call?: Call | null;
  resource_digest?: string | null; integrity?: State; discovered?: State; activated?: State; executable?: State;
  dependencies?: string[] | null; dependency_healthy?: State; resources?: { name: string; size: number; kind: string }[];
  metadata?: object; activation_contexts?: object[]; runtime_evidence?: object; configuration_source?: string;
};
type OverviewData = {
  api: Snapshot & { build_revision: string | null; response_ms: number | null };
  agent_db: Snapshot; backend_db: Snapshot | null; workspace: Snapshot & { readable: State; writable: State };
  workers: Snapshot; runtime: Snapshot & { runs: Run[] };
  counts: Snapshot & {
    window_start: string; window_end: string; queued_tasks: number | null; running_runs: number | null;
    failed_tasks: number | null; expired_leases: number | null; recent_failures: Run[];
  };
};
type Event = { seq: number; turn: number; name: string; occurred_at: string };

const UNKNOWN = '未知';
const display = (value: ReactNode) => value === null || value === undefined || value === '' ? UNKNOWN : value;
const flag = (state: State | undefined) => ({ yes: '是', no: '否', unknown: UNKNOWN, not_applicable: '不适用' }[state ?? 'unknown']);
const date = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN') : UNKNOWN;
const segment = (value: string) => encodeURIComponent(value);
const link = (section: string, id: string) => '#/agent/' + section + '/' + segment(id);
const apiPath = (path: string) => '/agent/' + path;
const catalogNames = { providers: 'Provider', models: 'Model', tools: 'Tools', skills: 'Skills' } as const;
type Catalog = keyof typeof catalogNames;

function Fields({ rows }: { rows: [string, ReactNode][] }) {
  return <dl className="agent-fields">{rows.map(([label, value]) =>
    <div key={label}><dt>{label}</dt><dd>{display(value)}</dd></div>)}</dl>;
}

function Table({ headers, rows }: { headers: string[]; rows: { key: string; cells: ReactNode[] }[] }) {
  return rows.length ? <div className="table-wrap"><table className="agent-table">
    <thead><tr>{headers.map(header => <th scope="col" key={header}>{header}</th>)}</tr></thead>
    <tbody>{rows.map(({ key, cells }) => <tr key={key}>{cells.map((cell, i) => <td key={i}>{display(cell)}</td>)}</tr>)}</tbody>
  </table></div> : <p className="empty">暂无匹配记录</p>;
}

function Freshness({ observed }: { observed?: string | null }) {
  const [time, setTime] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setTime(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return observed ? <p className="note">{time - Date.parse(observed) > 120_000 ? '数据已过期 · ' : ''}观测于 {date(observed)}</p> : null;
}

function Resource<T>({ path, children, observed }: { path: string; children: (data: T) => ReactNode; observed?: (data: T) => string | null }) {
  const query = useResource<T>(apiPath(path));
  const [received, setReceived] = useState<string>();
  useEffect(() => { if (query.data) setReceived(new Date().toISOString()); }, [query.data]);
  return <section className="agent-resource">
    <div className="actions"><button type="button" onClick={query.refresh} disabled={query.loading}>刷新</button></div>
    {query.loading && <p role="status">正在读取…</p>}
    {query.error && <p className="error" role="alert">{query.error}</p>}
    {query.data && <><Freshness observed={observed?.(query.data) ?? received} />{children(query.data)}</>}
  </section>;
}

function Paginated<T>({ path, children }: { path: string; children: (items: T[]) => ReactNode }) {
  const [history, setHistory] = useState<string[]>([]);
  const cursor = history.at(-1);
  return <Resource<Page<T>> path={path + (cursor ? (path.includes('?') ? '&' : '?') + 'cursor=' + segment(cursor) : '')}
    observed={page => page.observed_at}>
    {page => <>{children(page.items)}<div className="actions agent-pagination">
      <button onClick={() => setHistory(items => items.slice(0, -1))} disabled={!history.length}>上一页</button>
      <span>第 {history.length + 1} 页</span>
      <button onClick={() => { if (page.next_cursor) setHistory(items => [...items, page.next_cursor!]); }} disabled={!page.next_cursor}>下一页</button>
    </div></>}
  </Resource>;
}

function SnapshotInfo({ value }: { value: Snapshot | null }) {
  return <Fields rows={[['状态', value ? ({ ok: '可观测', unavailable: '不可用', degraded: '部分可用', unknown: UNKNOWN }[value.status] ?? value.status) : UNKNOWN],
    ['来源', value?.source], ['观测时间', date(value?.observed_at)], ['异常原因', value?.reason_code ?? '—']]} />;
}

function RunTable({ runs }: { runs: Run[] }) {
  return <Table headers={['Run', '状态', 'Attempt', 'Worker', 'Execution', '租约', '开始', '结束', '错误分类']}
    rows={runs.map(run => ({ key: run.run_id, cells: [
      <a href={link('runs', run.run_id)}>{run.run_id}</a>, run.status, run.attempt,
      run.worker_id && <a href={link('workers', run.worker_id)}>{run.worker_id}</a>,
      run.execution?.execution_id, run.lease_status, date(run.started_at), date(run.completed_at), run.error_code ?? '—',
    ]}))} />;
}

function localRange(values: FormData) {
  const query: Record<string, string> = {};
  for (const [key, value] of values.entries()) {
    if (typeof value === 'string' && value.trim()) {
      query[key] = key === 'from_at' || key === 'to_at' ? new Date(value).toISOString() : value.trim();
    }
  }
  return new URLSearchParams(query).toString();
}

function Range() {
  return <><label>起始时间<input type="datetime-local" name="from_at" /></label>
    <label>结束时间<input type="datetime-local" name="to_at" /></label></>;
}

function Overview() {
  const [query, setQuery] = useState('');
  return <><h1>Agent 运行总览</h1>
    <form className="agent-filters" onSubmit={event => { event.preventDefault(); setQuery(localRange(new FormData(event.currentTarget))); }}>
      <Range /><button>应用时间范围</button>
    </form>
    <Resource<OverviewData> path={'overview?' + query} observed={data => data.api.observed_at}>{data => <>
      <div className="agent-grid">
        <article><h2>Agent API</h2><SnapshotInfo value={data.api} />
          <Fields rows={[['声明的 Build Revision', data.api.build_revision], ['Backend 往返耗时', data.api.response_ms == null ? UNKNOWN : data.api.response_ms + ' ms']]} /></article>
        <article><h2>Agent PostgreSQL</h2><SnapshotInfo value={data.agent_db} /></article>
        <article><h2>Backend 权益 PostgreSQL</h2><SnapshotInfo value={data.backend_db} /></article>
        <article><h2>Workspace</h2><SnapshotInfo value={data.workspace} />
          <Fields rows={[['根目录可读取', flag(data.workspace.readable)], ['写入能力', flag(data.workspace.writable)]]} /></article>
        <article><h2>Worker</h2><SnapshotInfo value={data.workers} /><a href="#/agent/workers">查看 Worker 心跳和租约</a></article>
        <article><h2>任务与租约</h2><SnapshotInfo value={data.counts} />
          <Fields rows={[['统计时间窗', date(data.counts.window_start) + ' 至 ' + date(data.counts.window_end)],
            ['当前排队任务', data.counts.queued_tasks], ['当前执行中 Run', data.counts.running_runs],
            ['窗口内失败任务', data.counts.failed_tasks], ['当前超时租约', data.counts.expired_leases]]} /></article>
      </div>
      <WorkerEvidence />
      <h2>最近持久化 Run</h2><SnapshotInfo value={data.runtime} /><RunTable runs={data.runtime.runs} />
      <h2>时间窗内最近失败</h2><RunTable runs={data.counts.recent_failures} />
    </>}</Resource>
    <AgentOperationsOverview />
  </>;
}

function Workers({ id }: { id?: string }) {
  return <><h1>{id ? 'Worker 详情' : 'Worker 执行记录'}</h1><WorkerEvidence workerId={id} />
    <p className="note">状态根据持久化租约推导。空闲 Worker 和实例在线状态未知。</p>
    {id ? <Resource<Worker> path={'workers/' + segment(id)}>{worker => <>
      <Fields rows={[['Worker ID', worker.worker_id], ['最近已记录活动', date(worker.last_activity)],
        ['状态', worker.state === 'lease_observed' ? '存在有效租约' : UNKNOWN], ['活跃 Execution', worker.active_executions],
        ['超时租约', worker.expired_leases]]} />
      <RunTable runs={[worker.latest_run]} />
    </>}</Resource> : <Paginated<Worker> path="workers">{items => <Table
      headers={['Worker', '最近活动', '最近关联 Run', '状态', '活跃 Execution', '超时租约']}
      rows={items.map(w => ({ key: w.worker_id, cells: [<a href={link('workers', w.worker_id)}>{w.worker_id}</a>,
        date(w.last_activity), <a href={link('runs', w.latest_run.run_id)}>{w.latest_run.run_id}</a>,
        w.state === 'lease_observed' ? '存在有效租约' : UNKNOWN, w.active_executions, w.expired_leases] }))} />}
    </Paginated>}
  </>;
}

const entryId = (kind: Catalog, item: CatalogEntry) => ({
  providers: item.provider_id, models: item.model_id, tools: item.tool_id, skills: item.name,
}[kind]) ?? '';

const stateLabels: Record<string, string> = {
  registered: '已注册', configured: '已配置', loaded: '已加载（见来源）', deployed: '已部署',
  reachable: '可访问', healthy: '健康', authorized: '指定 Policy 授权',
};

function EvidenceTable({ states }: { states: States }) {
  return <Table headers={['状态维度', '状态', '来源', '观测时间', '配置修订', 'Worker']}
    rows={Object.entries(stateLabels).map(([name, label]) => ({
      key: name, cells: [label, flag(states[name]?.state), states[name]?.source, date(states[name]?.observed_at),
        states[name]?.config_revision, states[name]?.worker_id],
    }))} />;
}

function CatalogList({ kind }: { kind: Catalog }) {
  const [query, setQuery] = useState('');
  return <><h1>{catalogNames[kind]}</h1>
    <form className="agent-filters" onSubmit={event => {
      event.preventDefault();
      setQuery(localRange(new FormData(event.currentTarget)));
    }}><label>搜索 ID<input name="search" maxLength={100} /></label>
      <label>ID 排序<select name="order"><option value="asc">升序</option><option value="desc">降序</option></select></label>
      <button>搜索</button></form>
    <Paginated<CatalogEntry> key={kind + query} path={kind + '?' + query}>{items => <AgentHealthSummary targets={items.map(item => ({
      kind: kind === 'providers' ? 'provider' : kind === 'models' ? 'model' : kind === 'tools' ? 'tool' : 'skill', target_id: entryId(kind, item),
    }))}><Table
      headers={['ID', '名称', 'Provider / 来源', '已注册', '已加载', '最近检查']}
      rows={items.map(item => {
        const id = entryId(kind, item);
        return { key: id, cells: [<a href={link(kind, id)}>{id}</a>, item.label ?? item.name ?? id,
          kind === 'models' && item.provider_id ? <a href={link('providers', item.provider_id)}>{item.provider_id}</a> : item.source ?? item.protocol,
          flag(item.states.registered?.state), flag(item.states.loaded?.state),
          <CurrentHealth kind={kind === 'providers' ? 'provider' : kind === 'models' ? 'model' : kind === 'tools' ? 'tool' : 'skill'} id={id} />] };
      })} /></AgentHealthSummary>}
    </Paginated>
  </>;
}

function SkillResources({ entry }: { entry: CatalogEntry }) {
  const [open, setOpen] = useState(false);
  return <>
    <Fields rows={[['来源', entry.configuration_source ?? entry.source], ['资源摘要', entry.resource_digest], ['完整性', flag(entry.integrity)],
      ['已发现', flag(entry.discovered)], ['已激活', flag(entry.activated)], ['允许执行第一方工厂', flag(entry.executable)],
      ['依赖', entry.dependencies?.join('、')], ['依赖健康', flag(entry.dependency_healthy)]]} />
    <h2>References 与 Scripts</h2>
    <details><summary>Metadata 与激活上下文</summary><pre>{JSON.stringify({ metadata: entry.metadata, activations: entry.activation_contexts }, null, 2)}</pre></details>
    <Table headers={['文件', '类型', '字节']} rows={(entry.resources ?? []).map(row =>
      ({ key: row.name, cells: [row.name, row.kind, row.size] }))} />
    <button onClick={() => setOpen(!open)} disabled={!entry.resource_digest || entry.integrity !== 'yes'}>
      {open ? '收起' : '预览'} SKILL.md
    </button>
    {open && entry.resource_digest && <Resource<{ render_safe_markdown: string }>
      path={'skills/' + segment(entry.name ?? '') + '/document?resource_digest=' + segment(entry.resource_digest)}>
      {doc => <pre className="agent-preview">{doc.render_safe_markdown}</pre>}
    </Resource>}
  </>;
}

function CatalogDetail({ kind, id }: { kind: Catalog; id: string }) {
  const [policy, setPolicy] = useState('');
  const [run, setRun] = useState('');
  const params = new URLSearchParams();
  if (policy) params.set('policy_revision', policy);
  if (run && kind === 'tools') params.set('run_id', run);
  return <><h1>{catalogNames[kind]} 详情</h1><p><a href={'#/agent/' + kind}>返回列表</a></p>
    <p><a href="#/agent/config">配置候选、版本差异与发布</a></p>
    {kind !== 'providers' && <form className="agent-filters" onSubmit={event => {
      event.preventDefault(); setPolicy(String(new FormData(event.currentTarget).get('policy_revision') ?? '').trim());
    }}><label>对照已发布的 Policy 版本<input name="policy_revision" maxLength={255} /></label><button>查询授权匹配</button></form>}
    {kind === 'tools' && <form onSubmit={event => { event.preventDefault(); setRun(String(new FormData(event.currentTarget).get('run_id') ?? '').trim()); }}>
      <label>Run 上下文<input name="run_id" maxLength={255} /></label><button>查询运行能力</button></form>}
    <Resource<CatalogEntry> path={kind + '/' + segment(id) + '?' + params}
      observed={item => item.states.registered?.observed_at}>
      {item => <>
        <h2>{item.label ?? item.name ?? id}</h2>{item.description && <p>{item.description}</p>}
        {kind === 'providers' && <Fields rows={[['Provider ID', item.provider_id], ['协议', item.protocol], ['Base URL', item.base_url],
          ['凭据存在', item.credential_present ? '是' : '否'], ['配置启用', item.enabled ? '是' : '否'],
          ['关联模型', item.model_ids?.length ? <ul>{item.model_ids.map(model =>
            <li key={model}><a href={link('models', model)}>{model}</a></li>)}</ul> : '无']]} />}
        {kind === 'models' && <><Fields rows={[['Model ID', item.model_id],
          ['Provider ID', item.provider_id && <a href={link('providers', item.provider_id)}>{item.provider_id}</a>],
          ['上游 Model ID', item.upstream_model_id], ['Brand', item.brand], ['默认用途', item.default_purposes?.join('、') || '无'],
          ['配置启用', item.enabled ? '是' : '否'], ['路由配置修订', item.config_revision], ['能力版本', item.capability_version]]} />
          <h2>能力规格</h2><Fields rows={Object.entries(item.capabilities ?? {}).map(([key, value]) =>
            [key, typeof value === 'boolean' ? (value ? '是' : '否') : value])} /></>}
        {kind === 'tools' && <><Fields rows={[['Tool ID', item.tool_id], ['来源', item.source], ['注册类型', item.registration],
          ['组装条件', item.conditions?.join('、') || '—'], ['Latent', flag(item.latent)], ['当前 Run 可调用', flag(item.run_callable)],
          ['能力版本', item.capability_version], ['Schema Digest', item.schema_digest]]} />
          <h2>参数 Schema</h2>{item.parameters_schema ? <pre className="agent-preview">{JSON.stringify(item.parameters_schema, null, 2)}</pre> : <p>{UNKNOWN}</p>}
          {item.runtime_evidence && <pre>{JSON.stringify(item.runtime_evidence, null, 2)}</pre>}
          <h2>最近一次已观测调用</h2>{item.latest_call ? <CallTable calls={[item.latest_call]} /> : <p>{UNKNOWN}</p>}</>}
        {kind === 'skills' && <SkillResources entry={item} />}
        {(kind === 'providers' || kind === 'models') && <>
          <h2>最近已观测的模型调用</h2>
          {item.latest_observation ? <Fields rows={[
            ['模型', <a href={link('models', item.latest_observation.model_id)}>{item.latest_observation.model_id}</a>],
            ['能力版本', item.latest_observation.capability_version], ['观测结果', item.latest_observation.outcome],
            ['观测时间', date(item.latest_observation.observed_at)], ['来源', item.latest_observation.source],
          ]} /> : <p>{UNKNOWN}</p>}
        </>}
        <h2>状态与证据</h2><EvidenceTable states={item.states} />
        <HealthChecks kind={kind === 'providers' ? 'provider' : kind === 'models' ? 'model' : kind === 'tools' ? 'tool' : 'skill'} id={id} />
      </>}
    </Resource>
  </>;
}

function CallTable({ calls }: { calls: Call[] }) {
  return <Table headers={['调用 ID', '能力', '版本', 'Execution', 'Run', '状态', '开始时间', '耗时 ms', '用量状态', '已知 Token', '失败原因']}
    rows={calls.map(call => ({ key: call.call_id, cells: [call.call_id,
      call.capability_id && call.kind !== 'unknown'
        ? <a href={link(call.kind === 'tool' ? 'tools' : call.kind === 'skill' ? 'skills' : 'models',
          call.kind === 'tool' ? call.capability_id : call.capability_id.replace(/^[^:]*:/, ''))}>{call.capability_id}</a>
        : call.capability_id, call.capability_version, call.execution_id, <a href={link('runs', call.run_id)}>{call.run_id}</a>,
        call.status, date(call.started_at), call.duration_ms, call.usage_status, call.known_tokens, call.failure_reason ?? '未知'] }))} />;
}

const taskFilters = [
  ['task_id', 'Task ID'], ['run_id', 'Run ID'], ['user_id', '用户 ID'], ['worker_id', 'Worker ID'],
  ['status', '执行状态'], ['model_id', '实际调用 Model ID'], ['tool_id', '实际调用 Tool ID'],
] as const;

function Tasks() {
  const [query, setQuery] = useState('');
  return <><h1>Task / Run 监控</h1>
    <form className="agent-filters" onSubmit={event => { event.preventDefault(); setQuery(localRange(new FormData(event.currentTarget))); }}>
      {taskFilters.map(([name, label]) => <label key={name}>{label}<input name={name} maxLength={255} /></label>)}
      <Range /><label>创建时间排序<select name="order"><option value="desc">从新到旧</option>
        <option value="asc">从旧到新</option></select></label><button>筛选</button>
    </form>
    <p className="note">默认近 24 小时。Model 和 Tool 筛选使用已开始调用的事实。</p>
    <Paginated<Task> key={query} path={'tasks?' + query}>{items => <Table
      headers={['Task', '用户', '模式', '请求模型', '状态', '创建时间', '最近 Run', '失败分类']}
      rows={items.map(task => ({ key: task.task_id, cells: [<a href={link('tasks', task.task_id)}>{task.task_id}</a>,
        task.owner_id, task.mode, task.requested_model, task.status, date(task.created_at),
        task.latest_run && <a href={link('runs', task.latest_run.run_id)}>{task.latest_run.run_id}</a>, task.error_code ?? '—'] }))} />}
    </Paginated>
  </>;
}

function UsageSummary({ usage }: { usage: Usage | null }) {
  return <Fields rows={[['用量状态', usage?.status], ['实测 Token', usage?.measured_tokens], ['已知 Token', usage?.known_tokens],
    ['入账 Token', usage?.accounted_tokens], ['预留 Token', usage?.held_tokens], ['结算状态', usage?.settlement_status]]} />;
}

function TaskDetail({ id }: { id: string }) {
  const path = 'tasks/' + segment(id);
  return <><h1>Task 详情</h1>
    <Resource<Task> path={path}>{task => <>
      <Fields rows={[['Task ID', task.task_id], ['用户', task.owner_id], ['状态', task.status], ['创建时间', date(task.created_at)],
        ['模式', task.mode], ['请求模型', task.requested_model], ['失败分类', task.error_code ?? '—'],
        ['执行配置修订', task.execution_config_revision ?? '—'], ['等待原因', task.execution_wait_reason ?? '—']]} />
      <div className="agent-grid"><article><h2>Agent 观测用量</h2><UsageSummary usage={task.observed_usage} /></article>
        <article><h2>Backend 核验与入账</h2><UsageSummary usage={task.backend_usage} /></article></div>
      <Diagnosis kind="task" id={id} />
      <AgentControl kind="task" id={id} />
      <h2>Run 历史</h2><Paginated<Run> path={path + '/runs'}>{items => <RunTable runs={items} />}</Paginated>
    </>}</Resource>
  </>;
}

function RunDetail({ id }: { id: string }) {
  const path = 'runs/' + segment(id);
  const [kind, setKind] = useState('');
  return <><h1>Run 详情</h1>
    <Resource<Run> path={path}>{run => <>
      <Fields rows={[['Task', <a href={link('tasks', run.task_id)}>{run.task_id}</a>], ['Run ID', run.run_id],
        ['当前 Execution', run.execution?.execution_id], ['执行耗时 ms', run.duration_ms],
        ['Execution 已封闭', run.execution ? (run.execution.sealed ? '是' : '否') : UNKNOWN]]} />
      <RunTable runs={[run]} />
      <Diagnosis kind="run" id={id} />
      <AgentControl kind="run" id={id} />
      <h2>Execution 历史</h2>
      <Table headers={['Execution ID', 'Worker', '已封闭']} rows={run.executions.map(item => ({
        key: item.execution_id, cells: [item.execution_id, <a href={link('workers', item.worker_id)}>{item.worker_id}</a>,
          item.sealed ? '是' : '否'],
      }))} />
      {run.executions_truncated && <p className="note">显示最近 100 次 Execution。</p>}
      <h2>模型、Tool 与 Skill 调用</h2>
      <label>调用类型<select value={kind} onChange={event => setKind(event.target.value)}>
        <option value="">全部</option><option value="model">Model</option><option value="tool">Tool</option><option value="skill">Skill</option>
      </select></label>
      <Paginated<Call> key={kind} path={path + '/calls' + (kind ? '?kind=' + kind : '')}>{items => <CallTable calls={items} />}</Paginated>
      <h2>Run Events</h2>
      <Paginated<Event> path={path + '/events'}>{items => <Table headers={['序列', '轮次', '事件类型', '发生时间']}
        rows={items.map(event => ({key: String(event.seq), cells: [event.seq, event.turn, event.name, date(event.occurred_at)]}))} />}</Paginated>
    </>}</Resource>
  </>;
}

export function AgentManagement({ route }: { route: string }) {
  const [, , section, encodedId] = route.split('/');
  let id: string | undefined;
  try { id = encodedId ? decodeURIComponent(encodedId) : undefined; } catch { return <p role="alert">无效的资源 ID</p>; }
  const catalog = Object.hasOwn(catalogNames, section) ? section as Catalog : undefined;
  return <div className="agent-management">
    <nav aria-label="Agent 管理" className="page-navigation">
      {([['', '运行总览'], ['providers', 'Provider'], ['models', 'Model'], ['tools', 'Tools'], ['skills', 'Skills'],
        ['tasks', 'Task / Run'], ['workers', 'Workers'], ['alerts', '告警'], ['audit', '管理审计'], ['config', '配置中心']] as const).map(([value, title]) => <a key={value} href={'#/agent' + (value ? '/' + value : '')}
        aria-current={(section ?? '') === value ? 'page' : undefined}>{title}</a>)}
    </nav>
    {catalog ? (id ? <CatalogDetail key={route} kind={catalog} id={id} /> : <CatalogList key={route} kind={catalog} />)
      : section === 'tasks' ? (id ? <TaskDetail key={route} id={id} /> : <Tasks />)
      : section === 'runs' && id ? <RunDetail key={route} id={id} />
      : section === 'workers' ? <Workers key={route} id={id} />
      : section === 'audit' ? <AgentAudit key={route} id={id} />
      : section === 'alerts' ? <AgentAlerts />
      : section === 'config' ? <AgentConfigCenter key={route} route={route} /> : <Overview />}
  </div>;
}
