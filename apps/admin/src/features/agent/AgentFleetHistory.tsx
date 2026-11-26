import { useState, type FormEvent } from 'react';
import { useResource } from '../../useResource';

type Capability = { id: string; kind: string; version?: string; scope: string };
type Evidence = {
  worker_id: string; digest: string; last_seen: string; current_health?: string; current_lifecycle?: string;
  current_instance_id?: string; current_started_at?: string; current_run_id?: string;
  manifest: { build_revision?: string; config_revision?: string; capabilities: Capability[] };
};

export function AgentFleetHistory() {
  const [filter, setFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [eventWorker, setEventWorker] = useState('');
  const [eventOffset, setEventOffset] = useState(0);
  const events = useResource<{ items: { worker_id: string; instance_id: string; kind: string; sequence: number;
    observed_at: string; run_id?: string; manifest_digest?: string }[]; next_offset?: number }>(
    '/agent/config/fleet/events?offset=' + eventOffset + '&worker_id=' + encodeURIComponent(eventWorker));
  const [selected, setSelected] = useState<Evidence[]>([]);
  const result = useResource<{ items: Evidence[]; next_offset?: number }>('/agent/config/fleet?offset=' + offset + filter);
  function filterFleet(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = new URLSearchParams();
    for (const [key, value] of new FormData(event.currentTarget)) {
      if (!value || typeof value !== 'string') continue;
      query.set(key, ['since', 'until'].includes(key) ? new Date(value).toISOString() : value.trim());
    }
    setOffset(0);
    setEventOffset(0);
    setEventWorker(query.get('worker_id') ?? '');
    setFilter('&' + query);
  }
  const [before, after] = selected;
  const facts = new Map<string, [string | undefined, string | undefined]>();
  before?.manifest.capabilities.forEach(item => facts.set(item.kind + '/' + item.id, [item.version ?? item.scope, undefined]));
  after?.manifest.capabilities.forEach(item => {
    const id = item.kind + '/' + item.id;
    facts.set(id, [facts.get(id)?.[0], item.version ?? item.scope]);
  });
  return <><h2>Worker Manifest 历史</h2>
    <form className="agent-filters" onSubmit={filterFleet}>
      <label>Worker ID<input name="worker_id" /></label><label>Build<input name="build" /></label>
      <label>配置修订<input name="config_revision" /></label><label>开始<input name="since" type="datetime-local" /></label>
      <label>结束<input name="until" type="datetime-local" /></label><button>查询</button>
    </form>
    {result.error && <p role="alert">{result.error}</p>}
    {result.data?.items.map(item => <article key={item.worker_id + item.digest}>
      <p>{item.worker_id} · {item.last_seen} · {item.current_lifecycle ?? '历史 Manifest'}</p>
      <p>{item.manifest.build_revision} · {item.manifest.config_revision} · {item.digest}</p>
      {item.current_instance_id && <p>当前实例 {item.current_instance_id} · {item.current_started_at} · {item.current_health}</p>}
      {item.current_run_id && <a href={'#/agent/runs/' + encodeURIComponent(item.current_run_id)}>打开当前 Run</a>}
      {' '}<button onClick={() => setSelected(list => [...list.slice(-1), item])}>加入比较</button>
    </article>)}
    <button disabled={!offset} onClick={() => setOffset(value => Math.max(value - 5, 0))}>上一页</button>
    <button disabled={result.data?.next_offset == null} onClick={() => setOffset(result.data?.next_offset ?? 0)}>下一页</button>
    <h3>Worker 生命周期</h3>
    {events.error && <p role="alert">{events.error}</p>}
    <ul>{events.data?.items.map(item => <li key={[item.worker_id,item.instance_id,item.sequence,item.kind].join('/')}>
      {item.observed_at} · {item.worker_id} · {item.kind} · {item.instance_id}
      {item.run_id && <> · <a href={'#/agent/runs/' + encodeURIComponent(item.run_id)}>{item.run_id}</a></>}
    </li>)}</ul>
    <button disabled={!eventOffset} onClick={() => setEventOffset(value => Math.max(value - 20, 0))}>上一页事件</button>
    <button disabled={events.data?.next_offset == null} onClick={() => setEventOffset(events.data?.next_offset ?? 0)}>下一页事件</button>
    {before && after && <><h3>Manifest 能力差异</h3><p>{before.digest} → {after.digest}</p>
      <ul>{[...facts].filter(([, [left, right]]) => left !== right).map(([id, [left, right]]) =>
        <li key={id}>{id} · {left ?? '未上报'} → {right ?? '未上报'}</li>)}</ul></>}
  </>;
}
