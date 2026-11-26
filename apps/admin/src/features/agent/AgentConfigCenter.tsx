import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api';
import { useResource } from '../../useResource';
import { AgentFleetHistory } from './AgentFleetHistory';
import { AgentArtifactHistory } from './AgentArtifactHistory';
import { AgentConfigForm, type ConfigSpec } from './AgentConfigForm';

type Spec = ConfigSpec;
type Impact = { policies: string[]; affected_grants: number; impacted_owners: number; unknown: boolean };
type Operation = { operation_id: string; action: string; revision_id: string | null; before_revision: string | null;
  status: string; blockers: string[]; worker_ids: string[]; confirmed_workers: string[]; queued_tasks: number | null;
  active_runs: number | null; open_outbox: number | null; impact?: Impact; approval_ref?: string; reason: string; validation_digest?: string;
  queued_requiring_prior_worker?: number; runs_requiring_prior_worker?: number;
  compatible_workers?: number; unconfirmed_workers?: number };
type Revision = { revision_id: string; revision_number: number; config_digest: string; base_revision: string | null;
  status: string; spec: Spec; reason: string; validation_id: string | null };
type Index = { write_enabled: boolean; active_revision: string | null; desired_revision: string | null; admission_paused: boolean;
  pause_operation_id?: string; pause_reason?: string; deployment: Operation | null; revisions: Revision[]; history: Operation[] };

const ROOT = '/agent/config';
const revLink = (value: string) => '#/agent/config/' + encodeURIComponent(value);
const opLink = (value: string) => '#/agent/config/operations/' + encodeURIComponent(value);
const emptySpec: Spec = {
  schema_version: 1, build_revision: '', runtime_version: '', providers: [], models: [], defaults: {}, tools: [], skills: [],
};
const reasons: Record<string, string> = {
  CONFIG_WRITE_DISABLED: '配置写入开关关闭',
  WAITING_FOR_EFFECTIVE_WORKERS: '等待目标 Worker 加载并上报正确版本',
  LEGACY_TASKS_REQUIRE_DRAIN: '有未绑定兼容版本的旧任务，需要先排空',
  REQUIRES_POLICY_RELEASE: '现行用户权益依赖不同的能力版本，需走原套餐发布和分配流程',
  REQUIRES_OLD_WORKER: '仍有存量任务依赖旧版本 Worker',
  AFFECTED_GRANTS_REQUIRE_DRAIN: '仍有受影响且未关闭的 Grant，需等待原流程排空',
  CONFIG_POLICY_EVIDENCE_CHANGED: '当前权益证据发生变化或不完整',
  CONFIG_RESULT_UNCONFIRMED: '结果待对账，请保留原操作 ID',
  CONFIG_CAS_CONFLICT: '正式修订已变化，请刷新后重新验证',
  ISOLATED_NETWORK_PROOF_REQUIRED: '缺少隔离环境的连通性与模型检查证明',
};
function operationText(op: Operation) {
  return <><dl className="agent-fields">
    <div><dt>操作 ID</dt><dd>{op.operation_id}</dd></div><div><dt>阶段</dt><dd>{op.action} · {op.status}</dd></div>
    <div><dt>正式修订（发起时）</dt><dd>{op.before_revision ?? '未启用'}</dd></div>
    <div><dt>目标修订或部署</dt><dd>{op.revision_id ?? '—'}</dd></div>
    <div><dt>目标 / 确认 Worker</dt><dd>{op.confirmed_workers.length} / {op.worker_ids.length}</dd></div>
    <div><dt>排队 / 执行 / 未完成 Outbox</dt><dd>{op.queued_tasks ?? '未知'} / {op.active_runs ?? '未知'} / {op.open_outbox ?? '未知'}</dd></div>
    {op.compatible_workers != null && <>
      <div><dt>需要保留旧版本或排空的排队任务 / Run</dt><dd>{op.queued_requiring_prior_worker} / {op.runs_requiring_prior_worker}</dd></div>
      <div><dt>匹配目标版本 / 证据未匹配的 Worker</dt><dd>{op.compatible_workers} / {op.unconfirmed_workers}</dd></div>
    </>}
    <div><dt>验证摘要</dt><dd>{op.validation_digest ?? "未知"}</dd></div><div><dt>审批引用</dt><dd>{op.approval_ref ?? '—'}</dd></div><div><dt>原因</dt><dd>{op.reason}</dd></div>
  </dl>
  {op.blockers.length > 0 && <ul>{op.blockers.map(value => <li key={value}>{reasons[value] ?? value}</li>)}</ul>}
  {op.worker_ids.length > 0 && <ul>{op.worker_ids.map(worker => <li key={worker}>
    <a href={'#/agent/workers/' + encodeURIComponent(worker)}>{worker}</a> · {op.confirmed_workers.includes(worker) ? '已生效' : '待确认'}
  </li>)}</ul>}
  {op.impact && <p>受影响 Owner {op.impact.impacted_owners} · 未关闭且受影响的 Grant {op.impact.affected_grants} ·
    Policy {op.impact.policies.join('、') || '—'} {op.impact.unknown ? '（证据不完整）' : ''}</p>}</>;
}

function useOperation(refresh: () => void) {
  const [recent, setRecent] = useState<Operation>();
  const [pending, setPending] = useState<{ path: string; data: object; id: string }>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(path: string, data: object, replayId?: string) {
    if (busy) return;
    setBusy(true); setError('');
    const id = replayId ?? crypto.randomUUID();
    setPending({ path, data, id });
    try {
      const value = await api<Operation>(ROOT + path, { method: 'POST', body: JSON.stringify({ ...data, operation_id: id }) });
      setRecent(value); setPending(undefined); refresh();
    } catch (err) { setError((err as Error).message); if (err instanceof ApiError && err.status < 500) setPending(undefined); }
    finally { setBusy(false); }
  }
  const output = <>
    {error && <p role="alert">{reasons[error] ?? error}</p>}
    {pending && !busy && <p>操作 {pending.id} · <button onClick={() => void submit(pending.path, pending.data, pending.id)}>使用原操作 ID 重试</button>
      {' '}<a href={opLink(pending.id)}>查询状态</a></p>}
    {recent && <article><h2>最近操作</h2>{operationText(recent)} <a href={opLink(recent.operation_id)}>发布详情</a></article>}
  </>;
  return { submit, busy: busy || !!pending, output };
}
const value = (form: FormData, name: string) => String(form.get(name) ?? '').trim();

function CandidateEditor({ base, submit, busy }: { base?: Revision; submit: (path: string, data: object) => Promise<void>; busy: boolean }) {
  const [spec, setSpec] = useState(JSON.stringify(base?.spec ?? emptySpec, null, 2));
  const [error, setError] = useState('');
  const [mode, setMode] = useState('form');
  const [preview, setPreview] = useState<object>();
  const [prepared, setPrepared] = useState<object>();
  const [checking, setChecking] = useState(false);
  let parsed: Spec | undefined;
  try {
    const candidate = JSON.parse(spec);
    if (Array.isArray(candidate.providers) && Array.isArray(candidate.models) && candidate.defaults &&
        Array.isArray(candidate.tools) && Array.isArray(candidate.skills)) parsed = candidate;
  } catch { /* The advanced editor displays its parse error on submission. */ }
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setChecking(true); setPrepared(undefined);
    const form = new FormData(event.currentTarget);
    void (async () => {
      try {
        const body = { operation_id: crypto.randomUUID(), base_revision: base?.revision_id ?? null,
          reason: value(form, 'reason'), spec: JSON.parse(spec) };
        const result = await api<object>(ROOT + '/preview', { method: 'POST', body: JSON.stringify(body) });
        setPreview(result);
        setPrepared(body);
      } catch (failure) { setError((failure as Error).message); }
      finally { setChecking(false); }
    })();
  }
  return <details><summary>{base ? '基于此版本创建新候选' : '创建初始候选'}</summary>
    <form className="agent-filters" onSubmit={save} onChange={() => { setPrepared(undefined); setPreview(undefined); }}>
      <label>导入完整部署 Spec<input type="file" accept=".json" disabled={busy} onChange={async event => {
        try {
          const file = event.target.files?.[0];
          if (!file) return;
          if (file.size > 524288) throw new Error('配置文件超过大小限制');
          const imported = JSON.parse(await file.text());
          setSpec(JSON.stringify(imported.spec ?? imported, null, 2)); setPreview(undefined); setError('');
        } catch (failure) { setError((failure as Error).message); }
      }} /></label>
      <label>编辑方式<select value={mode} onChange={event => setMode(event.target.value)}><option value="form">表单</option><option value="json">JSON 高级配置</option></select></label>
      {mode === 'form' && parsed ? <AgentConfigForm spec={parsed} disabled={busy} change={data => { setSpec(JSON.stringify(data, null, 2)); setPreview(undefined); }} /> :
        <label>候选配置（仅填写 Secret Reference）<textarea rows={18} cols={68} value={spec} required onChange={event => { setSpec(event.target.value); setPreview(undefined); }} /></label>}
      <details><summary>候选变更预览</summary><pre>{JSON.stringify({ before: base?.spec ?? null, after: parsed }, null, 2)}</pre></details>
      {preview && <pre role="status">{JSON.stringify(preview, null, 2)}</pre>}
      <label>变更原因<input name="reason" required maxLength={256} /></label><button disabled={busy || checking}>检查依赖并预览</button>
      <button type="button" disabled={busy || checking || !prepared} onClick={() => {
        if (prepared && window.confirm('确认按预览创建不可变修订？')) void submit('/revisions', prepared);
      }}>创建不可变修订</button>
    </form>{error && <p role="alert">{error}</p>}
  </details>;
}

function downloadSpec(revision: Revision) {
  const blob = new Blob([JSON.stringify({ revision_id: revision.revision_id, config_digest: revision.config_digest,
    spec: revision.spec }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'agent-config-' + revision.revision_id + '.json';
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function RevisionDetail({ revision, index, refresh }: { revision: Revision; index: Index; refresh: () => void }) {
  const op = useOperation(refresh);
  function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    let externalProof;
    try { externalProof = value(form, 'external_proof') ? JSON.parse(value(form, 'external_proof')) : undefined; }
    catch {
      (event.currentTarget.elements.namedItem('external_proof') as HTMLTextAreaElement).setCustomValidity('证明必须是有效 JSON');
      event.currentTarget.reportValidity(); return;
    }
    void op.submit('/revisions/' + revision.revision_id + '/approve', {
      validation_id: revision.validation_id, expected_active_revision: index.active_revision,
      reason: value(form, 'reason'), external_proof: externalProof,
    });
  }
  const previous = useResource<Revision>(ROOT + '/revisions/' + encodeURIComponent(revision.base_revision ?? revision.revision_id));
  function submitValidation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const proof = JSON.parse(value(form, 'proof'));
      void op.submit('/revisions/' + revision.revision_id + '/validate',
        { proof, expected_active_revision: index.active_revision, reason: value(form, 'reason') });
    } catch { (event.currentTarget.elements.namedItem('proof') as HTMLTextAreaElement).setCustomValidity('证明必须是有效 JSON'); event.currentTarget.reportValidity(); }
  }
  function beginSwitch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const action = value(form, 'action');
    const workers = value(form, 'workers').split(/[\s,，]+/).filter(Boolean);
    if (!window.confirm('确认对这些 Worker 发起' + (action === 'rollback' ? '回滚' : '发布') + '？' + workers.join('、'))) return;
    void op.submit('/revisions/' + revision.revision_id + '/' + action, {
      validation_id: revision.validation_id, expected_active_revision: index.active_revision,
      worker_ids: workers, approval_ref: value(form, 'approval'), reason: value(form, 'reason'),
    });
  }
  return <><h2>修订 {revision.revision_number} · {revision.status}</h2>
    <p>{revision.revision_id} · {revision.config_digest}</p><p>{revision.reason}</p>
    <p>Build {revision.spec.build_revision} · Runtime {revision.spec.runtime_version}</p>
    <button type="button" onClick={() => downloadSpec(revision)}>下载部署清单</button>
    <CandidateEditor key={revision.revision_id} base={revision} submit={op.submit} busy={op.busy || !index.write_enabled} />
    <details><summary>版本差异与产物</summary>
      {revision.base_revision && <p>基准 <a href={revLink(revision.base_revision)}>{revision.base_revision}</a></p>}
      {(Object.keys(revision.spec) as (keyof Spec)[]).filter(key => !revision.base_revision ||
        JSON.stringify(previous.data?.spec[key]) !== JSON.stringify(revision.spec[key])).map(key =>
        <div key={key}><h3>{key}</h3>{revision.base_revision && <pre className="agent-preview">{JSON.stringify(previous.data?.spec[key], null, 2)}</pre>}
          <pre className="agent-preview">{JSON.stringify(revision.spec[key], null, 2)}</pre></div>)}
    </details>
    {revision.spec.tools.map(item => <AgentArtifactHistory key={item.id} revision={revision.revision_id}
      base={revision.base_revision} kind="tool" artifactId={item.id} />)}
    {revision.spec.skills.map(item => <AgentArtifactHistory key={item.id} revision={revision.revision_id}
      base={revision.base_revision} kind="skill" artifactId={item.id} />)}
    <form className="agent-filters" onSubmit={submitValidation}>
      <label>隔离验证签名证明<textarea name="proof" required rows={4} cols={48}
        onChange={event => event.currentTarget.setCustomValidity('')} /></label>
      <label>验证原因<input name="reason" required maxLength={256} /></label><button disabled={op.busy || !index.write_enabled}>验证候选</button>
    </form>
    <form className="agent-filters" onSubmit={approve}>
      <label>独立审批签名证明（启用身份分离时填写）<textarea name="external_proof" rows={4}
        onChange={event => event.currentTarget.setCustomValidity('')} /></label>
      <label>审批依据<input name="reason" required maxLength={256} /></label>
      <button disabled={op.busy || !index.write_enabled || revision.status !== 'validated' || !revision.validation_id}>记录审批</button>
    </form>
    <form className="agent-filters" onSubmit={beginSwitch}>
      <label>动作<select name="action"><option value="activate">发布</option><option value="rollback">回滚至此版本</option></select></label>
      <label>本批 Worker ID<input name="workers" required /></label>
      <label>审批引用<input name="approval" required maxLength={256} /></label>
      <label>操作原因<input name="reason" required maxLength={256} /></label>
      <button disabled={op.busy || !index.write_enabled || revision.status !== 'validated' || !revision.validation_id}>发起操作</button>
    </form>
    {op.output}
  </>;
}

function DeploymentDetail({ id, writeEnabled }: { id: string; writeEnabled: boolean }) {
  const data = useResource<Operation>(ROOT + '/operations/' + encodeURIComponent(id));
  const op = useOperation(data.refresh);
  function act(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const action = value(form, 'action');
    if (action === 'pause' && !window.confirm('确认暂停这次部署？')) return;
    void op.submit('/deployments/' + id + '/' + action, { reason: value(form, 'reason') });
  }
  return <><h2>发布详情</h2><button onClick={data.refresh}>刷新</button>
    {data.loading && <p role="status">正在读取…</p>}{data.error && <p role="alert">{reasons[data.error] ?? data.error}</p>}
    {data.data && operationText(data.data)}
    {data.data && ['activate', 'rollback'].includes(data.data.action) &&
      ['deploying', 'partially_deployed', 'rollback_pending', 'pending_reconcile'].includes(data.data.status) &&
      <form className="agent-filters" onSubmit={act}><label>操作<select name="action">
        <option value="reconcile">核验生效</option><option value="pause">暂停</option></select></label>
        <label>原因<input name="reason" required maxLength={256} /></label><button disabled={op.busy || !writeEnabled}>执行</button>
      </form>}
    {op.output}
  </>;
}

export function AgentConfigCenter({ route }: { route: string }) {
  const [, , , revision, operationId] = route.split('/');
  const query = useResource<Index>(ROOT + '/revisions');
  const detailPath = revision && revision !== 'operations' && revision !== 'fleet' ? ROOT + '/revisions/' + encodeURIComponent(revision) : undefined;
  const detail = useResource<Revision>(detailPath);
  const selected = detailPath ? detail.data : undefined;
  const op = useOperation(query.refresh);
  function refresh() {
    query.refresh();
    detail.refresh();
  }
  function admission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.data || !window.confirm('确认变更新任务准入状态？')) return;
    void op.submit('/admission', { expected_active_revision: query.data.active_revision,
      paused: !query.data.admission_paused, expected_pause_operation_id: query.data.pause_operation_id ?? null, reason: value(new FormData(event.currentTarget), 'reason') });
  }
  return <><h1>Agent 配置管理</h1><p><a href="#/agent/config">返回配置中心</a></p>
    {revision === 'fleet' ? <AgentFleetHistory /> : revision === 'operations' && operationId ? <DeploymentDetail key={operationId} id={operationId} writeEnabled={query.data?.write_enabled === true} /> : <>
      {query.loading && <p role="status">正在读取…</p>}{query.error && <p role="alert">{query.error}</p>}
      {query.data && <>
        {!query.data.write_enabled && <p role="status">配置写入关闭</p>}
        <p>正式修订：{query.data.active_revision ? <a href={revLink(query.data.active_revision)}>{query.data.active_revision}</a> : '未启用'}
          {' · '}期望修订：{query.data.desired_revision ?? '未启用'}</p>
        {query.data.pause_reason && <p>准入暂停原因 {query.data.pause_reason}</p>}
        {query.data.deployment && <p>当前部署 <a href={opLink(query.data.deployment.operation_id)}>{query.data.deployment.status}</a></p>}
        {detailPath ? <>
          {detail.loading && <p role="status">正在读取修订…</p>}
          {detail.error && <p role="alert">{reasons[detail.error] ?? detail.error}</p>}
          {selected && <RevisionDetail key={selected.revision_id} revision={selected} index={query.data} refresh={refresh} />}
        </> : <>
          {!query.data.revisions.length && <CandidateEditor submit={op.submit} busy={op.busy || !query.data.write_enabled} />}
          <p><a href="#/agent/config/fleet">Worker Manifest 历史</a></p>
          <h2>配置修订</h2><ul>{query.data.revisions.map(row => <li key={row.revision_id}>
            <a href={revLink(row.revision_id)}>修订 {row.revision_number}</a> · {row.status} · {row.reason}
          </li>)}</ul>
          <h2>发布与验证历史</h2><ul>{query.data.history.map(item => <li key={item.operation_id}>
            <a href={opLink(item.operation_id)}>{item.action} · {item.status}</a> · {item.reason}
          </li>)}</ul>
          <form className="agent-filters" onSubmit={admission}><label>准入变更原因<input name="reason" required maxLength={256} /></label>
            <button disabled={op.busy || !query.data.write_enabled}>{query.data.admission_paused ? '恢复新任务准入' : '暂停新任务准入'}</button>
          </form>{op.output}
        </>}
      </>}
    </>}
  </>;
}
