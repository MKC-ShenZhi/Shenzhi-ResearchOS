import { useResource } from '../../useResource';
import { AgentHealthSummary, CurrentHealth } from './AgentHealthSummary';
import type { Target } from './agent-api';

function CapabilityHealth({ section, kind }: { section: string; kind: Target['kind'] }) {
  const query = useResource<{ items: { provider_id?: string; model_id?: string; tool_id?: string; name?: string }[]; next_cursor: string | null }>('/agent/' + section + '?limit=10');
  const targets = (query.data?.items ?? []).map(item => ({ kind, target_id: item.model_id ?? item.tool_id ?? item.name ?? item.provider_id! }));
  return <article><h3><a href={'#/agent/' + section}>{section}</a></h3>
    {query.error && <p role="alert">{query.error}</p>}
    <AgentHealthSummary targets={targets}>{targets.map(item => <p key={item.target_id}>
      <a href={'#/agent/' + section + '/' + encodeURIComponent(item.target_id)}>{item.target_id}</a> · <CurrentHealth kind={kind} id={item.target_id} />
    </p>)}</AgentHealthSummary>
    {query.data?.next_cursor && <a href={'#/agent/' + section}>查看其余能力</a>}
  </article>;
}

export function AgentOperationsOverview() {
  const release = useResource<{ active_revision: string | null; desired_revision: string | null; admission_paused: boolean; deployment: { status: string } | null }>('/agent/config/revisions');
  const alerts = useResource<{ items: { alert_id: string; state: string; worker_id: string }[]; next_offset: number | null }>('/agent/alerts');
  return <section><h2>能力与运维状态</h2><div className="agent-grid">
    <CapabilityHealth section="providers" kind="provider" /><CapabilityHealth section="models" kind="model" />
    <CapabilityHealth section="tools" kind="tool" /><CapabilityHealth section="skills" kind="skill" />
    <article><h3><a href="#/agent/config">配置发布</a></h3>{release.error && <p role="alert">{release.error}</p>}
      {release.data && <><p>正式 {release.data.active_revision ?? '未启用'} · 期望 {release.data.desired_revision ?? '未启用'}</p>
        <p>{release.data.admission_paused ? '新任务准入已暂停' : '准入未暂停'} · {release.data.deployment?.status ?? '无发布操作'}</p></>}</article>
    <article><h3><a href="#/agent/alerts">告警</a></h3>{alerts.error && <p role="alert">{alerts.error}</p>}
      {alerts.data?.items.map(item => <p key={item.alert_id}><a href={'#/agent/workers/' + encodeURIComponent(item.worker_id)}>{item.worker_id}</a> · {item.state}</p>)}
      {alerts.data?.items.length === 0 && <p>暂无告警</p>}</article>
  </div></section>;
}
