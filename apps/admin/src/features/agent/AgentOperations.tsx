import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api';
import { useResource } from '../../useResource';

export function AgentControl({ kind, id }: { kind: 'task' | 'run' | 'worker' | 'alert'; id: string }) {
  const [pending, setPending] = useState<object>();
  const [busy, setBusy] = useState(false);
  const [output, setOutput] = useState('');
  const worker = useResource<{ state: string; deadline: string; active_runs: string[] }>(
    kind === 'worker' ? '/agent/worker-control/' + encodeURIComponent(id) : undefined);
  const cancellation = useResource<object>(kind === 'task' || kind === 'run'
    ? '/agent/control-status/' + kind + '/' + encodeURIComponent(id) : undefined);
  async function send(body: object) {
    setPending(body); setBusy(true); setOutput('');
    try {
      const result = await api<object>('/agent/actions', { method: 'POST', body: JSON.stringify(body) });
      setOutput(JSON.stringify(result, null, 2)); setPending(undefined); worker.refresh(); cancellation.refresh();
    } catch (failure) {
      setOutput((failure as Error).message);
      if (failure instanceof ApiError && failure.status < 500) setPending(undefined);
    }
    finally { setBusy(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!window.confirm('确认执行管理操作？')) return;
    void send({ operation_id: crypto.randomUUID(), kind, target_id: id, action: form.get('action'),
      reason: form.get('reason'), timeout_seconds: Number(form.get('timeout') ?? 300) });
  }
  return <section><h3>运行控制</h3>
    {worker.data && <p>Drain {worker.data.state} · 存量 Run {worker.data.active_runs.join('、') || '无'} · 截止 {worker.data.deadline ?? '无'}</p>}
    {worker.error && <p role="alert">{worker.error}</p>}
    {kind === 'worker' && <button onClick={worker.refresh}>刷新排空状态</button>}
    <form onSubmit={submit}><fieldset disabled={busy || !!pending}>
      <label>操作<select name="action">
        {kind === 'worker' ? <><option value="drain">排空 Worker</option><option value="resume">恢复接收任务</option></> :
          kind === 'alert' ? <><option value="acknowledge">确认告警</option><option value="close">关闭已恢复告警</option></> : <option value="cancel">请求取消</option>}
      </select></label>
      {kind === 'worker' && <label>等待超时（秒）<input name="timeout" type="number" min={10} max={86400} defaultValue={300} required /></label>}
      <label>原因<input name="reason" required maxLength={256} /></label><button>执行</button>
    </fieldset></form>
    {pending && !busy && <button onClick={() => void send(pending)}>使用原操作 ID 重试</button>}
    {output && <pre role="status">{output}</pre>}
    {(kind === 'task' || kind === 'run') && <p>取消请求由现有 Worker 协议处理。刷新详情核对任务终态、Execution 和结算状态。</p>}
    {(kind === 'task' || kind === 'run') && <><button onClick={cancellation.refresh}>刷新取消确认</button>
      {cancellation.data && <pre>{JSON.stringify(cancellation.data, null, 2)}</pre>}
      {cancellation.error && <p role="alert">{cancellation.error}</p>}</>}
  </section>;
}

type Alert = { alert_id: string; worker_id: string; state: string; opened_at: string; recovered_at: string | null };
export function AgentAlerts() {
  const [offset, setOffset] = useState(0);
  const query = useResource<{ items: Alert[]; next_offset: number | null; inspector_enabled: boolean }>('/agent/alerts?offset=' + offset);
  return <section><h2>Worker 告警</h2><button onClick={query.refresh}>刷新告警</button>
    {query.loading && <p role="status">读取中…</p>}{query.error && <p role="alert">{query.error}</p>}
    {query.data && !query.data.inspector_enabled && <p role="status">主动巡检关闭。当前 Worker 状态仍可通过最后心跳查询。</p>}
    {query.data?.items.length === 0 && <p>暂无告警</p>}
    {query.data?.items.map(item => <article key={item.alert_id}>
      <p><a href={'#/agent/workers/' + encodeURIComponent(item.worker_id)}>{item.worker_id}</a> · {item.state}</p>
      <p>{item.opened_at} · 恢复 {item.recovered_at ?? '尚未恢复'}</p>
      <AgentControl kind="alert" id={item.alert_id} />
    </article>)}
    <button disabled={!offset} onClick={() => setOffset(0)}>第一页</button>
    <button disabled={query.data?.next_offset == null} onClick={() => setOffset(query.data!.next_offset!)}>下一页</button>
  </section>;
}
