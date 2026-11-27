import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api';
import { useResource } from '../../useResource';
import { AgentConfigForm, type ConfigSpec } from './AgentConfigForm';

type Spec = ConfigSpec;
type Operation = {
  operation_id: string; action: string; revision_id: string | null; status: string;
  blockers: string[]; reason: string; validation_digest?: string;
};
type Revision = {
  revision_id: string; revision_number: number; config_digest: string; status: string;
  spec: Spec; reason: string; validation_id: string | null;
};
type Index = {
  write_enabled: boolean; active_revision: string | null; deployment: Operation | null;
  revisions: Revision[]; history: Operation[];
};

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
function OperationResult({ op }: { op: Operation }) {
  return <>
    <p>{op.action} · {op.status} · {op.reason}</p>
    <p>操作 ID {op.operation_id}</p>
    {op.validation_digest && <p>验证摘要 <code>{op.validation_digest}</code></p>}
    {op.revision_id && <p><a href={revLink(op.revision_id)}>查看修订</a></p>}
    {op.blockers.length > 0 && <ul>{op.blockers.map(value => <li key={value}>{reasons[value] ?? value}</li>)}</ul>}
  </>;
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
    {recent && <article><h3>最近操作</h3><OperationResult op={recent} /><a href={opLink(recent.operation_id)}>操作详情</a></article>}
  </>;
  return { submit, busy: busy || !!pending, output };
}
const value = (form: FormData, name: string) => String(form.get(name) ?? '').trim();

type Candidate = { base_revision: string | null; reason: string; spec: Spec };

function CandidateEditor({ base, submit, busy, writeEnabled }: {
  base?: Revision; submit: (path: string, data: Candidate) => Promise<void>; busy: boolean; writeEnabled: boolean;
}) {
  const [spec, setSpec] = useState(base?.spec ?? emptySpec);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<object>();
  const [prepared, setPrepared] = useState<Candidate>();
  const [checking, setChecking] = useState(false);
  const [importing, setImporting] = useState(false);
  const locked = busy || checking || importing || !writeEnabled;

  function clearPreview() {
    setPrepared(undefined);
    setPreview(undefined);
    setError('');
  }

  async function check(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked) return;
    clearPreview();
    setChecking(true);
    const body = { base_revision: base?.revision_id ?? null, reason: value(new FormData(event.currentTarget), 'reason'), spec };
    try {
      setPreview(await api<object>(ROOT + '/preview', {
        method: 'POST', body: JSON.stringify({ ...body, operation_id: crypto.randomUUID() }),
      }));
      setPrepared(body);
    } catch (failure) { setError((failure as Error).message); }
    finally { setChecking(false); }
  }

  return <details><summary>{base ? '基于此修订编辑 Provider / Model' : '创建初始候选'}</summary>
    <form className="agent-candidate" onSubmit={check} onChange={clearPreview}>
      {!base && <label>导入部署配置<input type="file" accept=".json" disabled={locked} onChange={async event => {
        const file = event.target.files?.[0];
        if (!file) return;
        setImporting(true);
        try {
          if (file.size > 524288) throw new Error('配置文件超过大小限制');
          const imported = JSON.parse(await file.text());
          const candidate = imported?.spec ?? imported;
          if (!candidate || !Array.isArray(candidate.providers) || !Array.isArray(candidate.models) ||
              !Array.isArray(candidate.tools) || !Array.isArray(candidate.skills) ||
              !candidate.defaults || typeof candidate.defaults !== 'object' || Array.isArray(candidate.defaults)) {
            throw new Error('请选择包含 Provider、Model、默认用途和资源引用的部署配置');
          }
          setSpec(candidate);
        } catch (failure) { setError((failure as Error).message); }
        finally { setImporting(false); }
      }} /></label>}
      <AgentConfigForm spec={spec} disabled={locked} change={setSpec} initializing={!base} />
      {preview && <details open><summary>配置变更预览</summary><pre className="agent-preview">{JSON.stringify(preview, null, 2)}</pre></details>}
      <div className="agent-filters">
        <label>变更原因<input name="reason" required maxLength={256} disabled={locked} /></label>
        <button disabled={locked}>检查依赖并预览</button>
        <button type="button" disabled={locked || !prepared} onClick={() => {
          if (prepared && window.confirm('确认按预览创建不可变修订？')) void submit('/revisions', prepared);
        }}>创建修订</button>
      </div>
    </form>{error && <p className="error" role="alert">{error}</p>}
  </details>;
}

function downloadSpec(revision: Revision) {
  const documentData = JSON.stringify({
    revision_id: revision.revision_id, config_digest: revision.config_digest, spec: revision.spec,
  }, null, 2);
  const url = URL.createObjectURL(new Blob([documentData], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'agent-config-' + revision.revision_id + '.json';
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function RevisionDetail({ revision, index, op }: { revision: Revision; index: Index; op: ReturnType<typeof useOperation> }) {
  const approvals = index.history.filter(item => item.revision_id === revision.revision_id && item.action === 'approve');
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
    const workers = value(form, 'workers').split(/[\s,，]+/).filter(Boolean);
    if (!window.confirm('确认发布至 Worker：' + workers.join('、') + '？')) return;
    void op.submit('/revisions/' + revision.revision_id + '/activate', {
      validation_id: revision.validation_id, expected_active_revision: index.active_revision,
      worker_ids: workers, approval_ref: value(form, 'approval'), reason: value(form, 'reason'),
    });
  }
  return <><h2>修订 {revision.revision_number} · {revision.status}</h2>
    <p>{revision.revision_id} · {revision.config_digest}</p><p>{revision.reason}</p>
    <button type="button" onClick={() => downloadSpec(revision)}>下载部署清单</button>
    {revision.validation_id && <p><a href={opLink(revision.validation_id)}>查看验证结果</a></p>}
    {approvals.length > 0 && <details><summary>审批记录</summary>
      <ul className="agent-revisions">{approvals.map(item => <li key={item.operation_id}>
        <a href={opLink(item.operation_id)}>{item.operation_id}</a> · {item.status}
      </li>)}</ul>
    </details>}
    <CandidateEditor key={revision.revision_id} base={revision} submit={op.submit}
      busy={op.busy} writeEnabled={index.write_enabled} />
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
      <label>本批 Worker ID<input name="workers" required /></label>
      <label>审批引用<input name="approval" required maxLength={256} /></label>
      <label>操作原因<input name="reason" required maxLength={256} /></label>
      <button disabled={op.busy || !index.write_enabled || revision.status !== 'validated' || !revision.validation_id}>发布修订</button>
    </form>
  </>;
}

function DeploymentDetail({ id, writeEnabled }: { id: string; writeEnabled: boolean }) {
  const data = useResource<Operation>(ROOT + '/operations/' + encodeURIComponent(id));
  const op = useOperation(data.refresh);
  function act(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void op.submit('/deployments/' + encodeURIComponent(id) + '/reconcile', { reason: value(form, 'reason') });
  }
  return <><h2>配置操作</h2><button type="button" onClick={data.refresh}>刷新</button>
    {data.loading && <p role="status">正在读取…</p>}{data.error && <p role="alert">{reasons[data.error] ?? data.error}</p>}
    {data.data && <OperationResult op={data.data} />}
    {data.data && ['activate', 'rollback'].includes(data.data.action) &&
      ['deploying', 'partially_deployed', 'rollback_pending', 'pending_reconcile'].includes(data.data.status) &&
      <form className="agent-filters" onSubmit={act}>
        <label>原因<input name="reason" required maxLength={256} /></label>
        <button disabled={op.busy || !writeEnabled}>核验生效</button>
      </form>}
    {op.output}
  </>;
}

export function AgentConfigCenter({ route }: { route: string }) {
  const [, , , revision, operationId] = route.split('/');
  const query = useResource<Index>(ROOT + '/revisions');
  const detail = useResource<Revision>(revision && revision !== 'operations' ? ROOT + '/revisions/' + encodeURIComponent(revision) : undefined);
  const op = useOperation(() => {
    query.refresh();
    detail.refresh();
  });
  return <>
    <h2>Provider / Model 配置</h2>
    {revision && <a href="#/agent/config">返回配置修订</a>}
    {query.loading && <p role="status">正在读取…</p>}
    {query.error && <p className="error" role="alert">{query.error}</p>}
    {query.data && <>
      {!query.data.write_enabled && <p role="status">配置写入关闭</p>}
      {revision === 'operations' && operationId ?
        <DeploymentDetail id={operationId} writeEnabled={query.data.write_enabled} /> : <>
          <p>正式修订 {query.data.active_revision ? <a href={revLink(query.data.active_revision)}>{query.data.active_revision}</a> : '未启用'}</p>
          {query.data.deployment && <p>当前发布 <a href={opLink(query.data.deployment.operation_id)}>{query.data.deployment.status}</a></p>}
          {revision ? <>
            {detail.loading && <p role="status">正在读取修订…</p>}
            {detail.error && <p className="error" role="alert">{reasons[detail.error] ?? detail.error}</p>}
            {detail.data && <RevisionDetail revision={detail.data} index={query.data} op={op} />}
          </> : <>
            {!query.data.revisions.length && !query.data.active_revision &&
              <CandidateEditor submit={op.submit} busy={op.busy} writeEnabled={query.data.write_enabled} />}
            <h3>配置修订</h3>
            {query.data.revisions.length ? <ul className="agent-revisions">{query.data.revisions.map(row => <li key={row.revision_id}>
              <a href={revLink(row.revision_id)}>修订 {row.revision_number}</a> · {row.status} · {row.reason}
            </li>)}</ul> : <p>暂无配置修订</p>}
          </>}
        </>}
    </>}
    {op.output}
  </>;
}
