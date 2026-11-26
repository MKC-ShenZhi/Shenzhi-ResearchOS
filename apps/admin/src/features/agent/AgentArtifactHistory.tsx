import { useState } from 'react';
import { useResource } from '../../useResource';

type Schema = { properties?: Record<string, Record<string, unknown>>; required?: string[] };
type FileEvidence = { id: string; digest: string; name: string; kind: string; size: number };
type Snapshot = {
  state: string; digest: string; resources?: FileEvidence[]; preview?: string;
  description?: string; parameters_schema?: Schema; schema_digest?: string;
  implementation_digest?: string; dependency_digests?: string[];
};

function changes(before: Schema, after: Schema) {
  const oldFields = before.properties ?? {};
  const newFields = after.properties ?? {};
  return [...new Set([...Object.keys(oldFields), ...Object.keys(newFields)])].sort().flatMap(name => {
    if (!Object.hasOwn(oldFields, name)) return [{ name, fields: '新增参数', risk: after.required?.includes(name) }];
    if (!Object.hasOwn(newFields, name)) return [{ name, fields: '删除参数', risk: true }];
    const older = oldFields[name];
    const newer = newFields[name];
    const changed = [...new Set([...Object.keys(older), ...Object.keys(newer)])]
      .filter(key => JSON.stringify(older[key]) !== JSON.stringify(newer[key]));
    const required = Boolean(before.required?.includes(name)) !== Boolean(after.required?.includes(name));
    if (!changed.length && !required) return [];
    return [{ name, fields: [...changed, ...(required ? ['required'] : [])].join('、'),
      risk: required || changed.some(key => !['description', 'title', 'examples'].includes(key)) }];
  });
}

export function AgentArtifactHistory({ revision, base, kind, artifactId }: {
  revision: string; base: string | null; kind: 'tool' | 'skill'; artifactId: string;
}) {
  const [resource, setResource] = useState<string>();
  const [comparison, setComparison] = useState(base ?? '');
  const query = new URLSearchParams({ kind, artifact_id: artifactId });
  const path = (id: string) => '/agent/config/revisions/' + encodeURIComponent(id) + '/artifacts?' + query;
  const current = useResource<Snapshot>(path(revision));
  const previous = useResource<Snapshot>(comparison ? path(comparison) : undefined);
  const document = useResource<Snapshot>(resource ? path(revision) + '&resource=' + encodeURIComponent(resource) : undefined);
  const now = current.data;
  const old = previous.data;
  const fileNames = [...new Set([...(old?.resources ?? []), ...(now?.resources ?? [])].map(file => file.name))].sort();
  return <details>
    <summary>{artifactId} · 历史证据</summary>
    <label>比较修订 ID <input value={comparison} onChange={event => setComparison(event.currentTarget.value.trim())} /></label>
    {current.loading && <p role="status">正在核验制品…</p>}
    {current.error && <p role="alert">{current.error}</p>}
    {now && <p>摘要 {now.digest} · {now.state}</p>}
    {comparison && <p>对照版本 {old?.state ?? (previous.error || '读取中')}</p>}
    {now?.state === 'available' && kind === 'tool' && <>
      <p>{now.description}</p>
      <p>Schema {now.schema_digest} · 实现 {now.implementation_digest}</p>
      <p>依赖 {now.dependency_digests?.join('、') || '—'}</p>
      <pre className="agent-preview">{JSON.stringify(now.parameters_schema, null, 2)}</pre>
      {old?.parameters_schema && now.parameters_schema && <ul>
        {old.description !== now.description && <li>工具描述已变更</li>}
        {changes(old.parameters_schema, now.parameters_schema).map(row => <li key={row.name}>
          {row.name} · {row.fields}{row.risk && ' · 可能不兼容'}
        </li>)}
      </ul>}
    </>}
    {now?.resources && <ul>{now.resources.map(file => <li key={file.id}>
      {file.kind === 'document' ? <button type="button" onClick={() => setResource(file.id)}>{file.name}</button> : file.name}
      {' · '}{file.digest} · {file.size} B
    </li>)}</ul>}
    {old?.resources && now?.resources && <ul>{fileNames.map(name => {
      const before = old.resources?.find(file => file.name === name);
      const after = now.resources?.find(file => file.name === name);
      return before?.digest !== after?.digest && <li key={name}>{name} · {before ? after ? '修改' : '删除' : '添加'}</li>;
    })}</ul>}
    {document.error && <p role="alert">{document.error}</p>}
    {document.data?.preview != null && <pre className="agent-preview">{document.data.preview}</pre>}
  </details>;
}
