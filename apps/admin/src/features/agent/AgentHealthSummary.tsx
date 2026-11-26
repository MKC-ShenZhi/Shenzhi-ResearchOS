import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { healthSummaries, type HealthSummary, type Target } from './agent-api';

const Context = createContext<{ items: HealthSummary[]; error: string; loading: boolean }>({ items: [], error: '', loading: true });
export function AgentHealthSummary({ targets, children }: { targets: Target[]; children: ReactNode }) {
  const key = JSON.stringify(targets);
  const [value, setValue] = useState({ items: [] as HealthSummary[], error: '', loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setValue({ items: [], error: '', loading: true });
    if (!targets.length) { setValue({ items: [], error: '', loading: false }); return; }
    void healthSummaries(JSON.parse(key), controller.signal).then(data => {
      setValue({ items: data.items, error: data.truncated ? '检查记录超过扫描上限' : '', loading: false });
    }).catch(failure => { if (!controller.signal.aborted) setValue({ items: [], error: failure.message, loading: false }); });
    return () => controller.abort();
  }, [key]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function CurrentHealth({ kind, id }: { kind: Target['kind']; id: string }) {
  const data = useContext(Context);
  const [time, setTime] = useState(Date.now);
  useEffect(() => { const timer = window.setInterval(() => setTime(Date.now()), 5000); return () => clearInterval(timer); }, []);
  if (data.loading) return <span>读取中…</span>;
  if (data.error) return <span title={data.error}>检查记录不可用</span>;
  const item = data.items.find(value => value.kind === kind && value.target_id === id);
  if (!item) return <span>未知</span>;
  const state = item.check && time >= Date.parse(item.check.expires_at) ? 'stale' : item.state;
  const labels: Record<string, string> = { pass: '通过', fail: '失败', unknown: '未知', unsupported: '不支持', stale: '已过期或版本不匹配', pending: '检查中' };
  return <span title={item.reason}>{state === 'pass' && item.check?.coverage !== 'complete' ? '部分步骤通过' : labels[state] ?? state}
    {item.check && <> · {item.check.profile}<br />{new Date(item.check.observed_at).toLocaleString('zh-CN')}</>}</span>;
}
