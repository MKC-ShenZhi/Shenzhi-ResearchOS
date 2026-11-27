import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { BookOpen, ExternalLink as ExternalLinkIcon, CircleHelp, X, Layers, ShieldCheck, Wrench } from 'lucide-react';
import { api } from '../../api';
import { useResource } from '../../useResource';
import './agent.css';

type State = 'yes' | 'no' | 'unknown' | 'not_applicable';
type Page<T> = { items: T[]; next_cursor: string | null };
type CatalogEntry = {
  provider_id?: string; model_id?: string; tool_id?: string; name?: string; label?: string; brand?: string;
  protocol?: string; base_url?: string; credential_present?: boolean; enabled?: boolean; model_ids?: string[];
  upstream_model_id?: string; capabilities?: Record<string, boolean | number | string | null>; default_purposes?: string[];
  parameters_schema?: object | null; conditions?: string[]; registration?: string;
  description?: string; source?: string; request_params?: Record<string, unknown>;
  resource_digest?: string | null; integrity?: State; dependencies?: string[] | null;
  resources?: { name: string; size: number; kind: string }[]; configuration_source?: string;
};

const UNKNOWN = '未知';
const display = (value: ReactNode) => value === null || value === undefined || value === '' ? UNKNOWN : value;
const flag = (state: State | undefined) => ({ yes: '是', no: '否', unknown: UNKNOWN, not_applicable: '不适用' }[state ?? 'unknown']);
const segment = (value: string) => encodeURIComponent(value);
const link = (section: string, id: string) => '#/agent/' + section + '/' + segment(id);
const apiPath = (path: string) => '/agent/' + path;
const catalogNames = { providers: 'Provider', models: 'Model', tools: 'Tools', skills: 'Skills' } as const;
type Catalog = keyof typeof catalogNames;
type Provider = { provider_id: string; base_url: string | null; credential_present: boolean; enabled: boolean };
type Model = CatalogEntry & {
  model_id: string; provider_id: string; upstream_model_id: string; label: string; enabled: boolean;
  capabilities: Record<'chat' | 'streaming' | 'tool_calling' | 'reasoning', boolean>;
};

const fieldHelp: Record<string, string> = {
  'Provider ID': '系统内用于识别供应商的唯一标识，模型通过它关联调用渠道。',
  'Provider': '提供该模型调用服务的供应商。同一模型在不同渠道可能使用不同的地址和价格。',
  'API 地址': '服务端向供应商发送模型请求时使用的基础地址。点击在新标签页打开。',
  'Base URL': '服务端向供应商发送模型请求时使用的基础地址。点击在新标签页打开。',
  '凭据状态': '表示服务端是否读取到非空 API Key。已配置仅说明凭据存在，有效性、余额和模型权限需通过实际请求验证。',
  '凭据存在': '表示服务端是否读取到非空 API Key。有效性、余额和模型权限需通过实际请求验证。',
  '启用状态': '当前配置是否启用此供应商或模型。实际调用还受凭据、模型能力和用户权益限制。',
  '配置启用': '当前配置是否启用此供应商或模型。实际调用还受凭据、模型能力和用户权益限制。',
  '协议': '与供应商通信时使用的 API 协议。',
  '关联模型': '当前 Registry 中归属于该供应商的模型。',
  '模型名称': '用于展示的模型名称。',
  '内部 Model ID': '深知内部识别、选择和路由模型使用的唯一标识。',
  '上游 Model ID': '发送给供应商 API 的实际模型名称，可能与内部 Model ID 不同。',
  '上下文长度': '优先显示供应商官网公布的上下文规格，K 表示千 Token，M 表示百万 Token。实际调用仍受运行配置与预算限制。',
  '最大输出 Token': '当前运行配置允许的输出上限。实际输出还受调用预算和供应商限制。',
  'Tool Calling': '模型是否声明支持结构化工具调用，由 Agent 执行工具并返回结果。',
  'Reasoning': '当前模型配置是否声明支持推理能力。',
  '流式输出': '是否支持在生成过程中逐步返回内容。',
  '默认用途': '该模型被显式指定为默认模型的用途。未指定时按 Registry 规则自动选择。',
  '数据来源': '参考价格资料的来源页面，点击可核对供应商公布的信息。',
  '核验时间': '最近一次核对价格资料的时间。尚未核验表示没有已核验资料。',
  '生效时间': '这份价格资料开始适用的时间。',
  '来源': '工具或技能目录记录的来源。',
  '完整性通过': '技能资源是否通过内容摘要等完整性校验。',
  '依赖': '技能声明需要的其他资源或能力。',
  'Tool ID': '系统内识别工具的唯一标识。',
  '注册类型': '工具在目录中的登记方式，例如静态注册或从调用记录中观测。',
  '可用条件': '组装或使用该工具所需的条件。',
};

function FieldLabel({ label }: { label: string }) {
  const id = useId();
  const [dismissed, setDismissed] = useState(false);
  const help = fieldHelp[label];
  if (!help) return <>{label}</>;
  return <span className="agent-field-help" onMouseEnter={() => setDismissed(false)}>
    <button type="button" className="agent-field-label" aria-describedby={dismissed ? undefined : id}
      onFocus={() => setDismissed(false)} onKeyDown={event => {
        if (event.key === 'Escape') setDismissed(true);
      }}>
      {label}<CircleHelp size={12} aria-hidden="true" />
    </button>
    {!dismissed && <span id={id} role="tooltip" className="agent-field-tooltip">{help}</span>}
  </span>;
}

function Fields({ rows }: { rows: [string, ReactNode][] }) {
  return <dl className="agent-fields">{rows.map(([label, value]) =>
    <div key={label}><dt><FieldLabel label={label} /></dt><dd>{display(value)}</dd></div>)}</dl>;
}

function Table({ headers, rows }: { headers: string[]; rows: { key: string; cells: ReactNode[] }[] }) {
  return rows.length ? <div className="table-wrap"><table className="agent-table">
    <thead><tr>{headers.map(header => <th scope="col" key={header}>{header}</th>)}</tr></thead>
    <tbody>{rows.map(({ key, cells }) => <tr key={key}>{cells.map((cell, i) => <td key={i}>{display(cell)}</td>)}</tr>)}</tbody>
  </table></div> : <p className="empty">暂无匹配记录</p>;
}

function Resource<T>({ path, children }: { path: string; children: (data: T) => ReactNode }) {
  const query = useResource<T>(apiPath(path));
  return <div className="agent-resource">
    <div className="actions"><button type="button" onClick={query.refresh} disabled={query.loading}>刷新</button></div>
    {query.loading && <p role="status">正在读取…</p>}
    {query.error && <p className="error" role="alert">{query.error}</p>}
    {query.data && children(query.data)}
  </div>;
}

function Paginated<T>({ path, children }: { path: string; children: (items: T[]) => ReactNode }) {
  const [history, setHistory] = useState<string[]>([]);
  const cursor = history.at(-1);
  return <Resource<Page<T>> path={path + (cursor ? (path.includes('?') ? '&' : '?') + 'cursor=' + segment(cursor) : '')}>
    {page => <>{children(page.items)}<div className="actions agent-pagination">
      <button onClick={() => setHistory(items => items.slice(0, -1))} disabled={!history.length}>上一页</button>
      <span>第 {history.length + 1} 页</span>
      <button onClick={() => { if (page.next_cursor) setHistory(items => [...items, page.next_cursor!]); }} disabled={!page.next_cursor}>下一页</button>
    </div></>}
  </Resource>;
}

async function readCatalog<T>(kind: 'providers' | 'models', signal: AbortSignal) {
  const items: T[] = [];
  const params = new URLSearchParams({ limit: '100' });
  for (;;) {
    const page = await api<Page<T>>(apiPath(kind) + '?' + params, { signal });
    items.push(...page.items);
    if (!page.next_cursor) return items;
    if (params.get('cursor') === page.next_cursor) throw new Error('目录分页异常，请刷新重试');
    params.set('cursor', page.next_cursor);
  }
}

function ProviderCatalog() {
  const [revision, setRevision] = useState(0);
  const [results, setResults] = useState<[Provider[], Model[]]>();
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [order, setOrder] = useState('asc');

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      readCatalog<Provider>('providers', controller.signal),
      readCatalog<Model>('models', controller.signal),
    ]).then(data => {
      if (!controller.signal.aborted) setResults(data);
    }).catch(failure => {
      if (!controller.signal.aborted) setError((failure as Error).message);
      controller.abort();
    });
    return () => controller.abort();
  }, [revision]);

  const loading = !results && !error;
  const term = search.trim().toLowerCase();
  const [providers, models] = results ?? [[], []];
  const groups = new Map<string, { provider?: Provider; models: Model[] }>(
    providers.map(provider => [provider.provider_id, { provider, models: [] }]),
  );
  for (const model of models) {
    const group = groups.get(model.provider_id) ?? { models: [] };
    group.models.push(model);
    groups.set(model.provider_id, group);
  }
  const compare = (left: string, right: string) => order === 'asc' ? left.localeCompare(right) : right.localeCompare(left);
  const visible = Array.from(groups, ([id, group]) => ({
    id, provider: group.provider, models: id.toLowerCase().includes(term) ? group.models :
      group.models.filter(model => [model.model_id, model.upstream_model_id, model.label]
        .some(value => value.toLowerCase().includes(term))),
  })).filter(group => group.id.toLowerCase().includes(term) || group.models.length)
    .sort((left, right) => compare(left.id, right.id));

  return <>
    <h2>供应商与模型目录</h2>
    <div className="agent-filters">
      <label>搜索供应商或模型<input type="search" value={search} maxLength={100} onChange={event => setSearch(event.target.value)} /></label>
      <label>ID 排序<select value={order} onChange={event => setOrder(event.target.value)}>
        <option value="asc">升序</option><option value="desc">降序</option>
      </select></label>
      <button type="button" disabled={loading} onClick={() => {
        setResults(undefined);
        setError('');
        setRevision(value => value + 1);
      }}>刷新</button>
    </div>
    {loading && <p role="status">正在读取…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {results && (visible.length ? <div className="agent-provider-groups">{visible.map(({ id, provider, models: entries }) =>
      <details className="agent-provider-group" key={id + term} open={!!term}>
        <summary><strong>{id}</strong><span>{entries.length} 个模型</span></summary>
        {provider && <p><a href={link('providers', id)}>供应商详情</a></p>}
        <Fields rows={[['Provider ID', id], ['API 地址', provider?.base_url && <ExternalLink url={provider.base_url}>{provider.base_url}</ExternalLink>],
          ['凭据状态', provider && (provider.credential_present ? '已配置' : '未配置')],
          ['启用状态', provider && (provider.enabled ? '启用' : '停用')]]} />
        {entries.length ? <ul>{entries.slice().sort((left, right) => compare(left.model_id, right.model_id)).map(model =>
          <li key={model.model_id}>
            <InlineModelDetails model={model} />
          </li>)}</ul> : <p>{term && models.some(model => model.provider_id === id) ? '暂无匹配模型' : '暂无模型'}</p>}
      </details>)}</div> : <p className="empty">暂无匹配记录</p>)}
  </>;
}

function CatalogList({ kind }: { kind: 'tools' | 'skills' }) {
  const [query, setQuery] = useState('');
  return <>
    <h2>{catalogNames[kind]}</h2>
    <form className="agent-filters" onSubmit={event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const params = new URLSearchParams({ order: String(form.get('order')) });
      const search = String(form.get('search') ?? '').trim();
      if (search) params.set('search', search);
      setQuery(params.toString());
    }}><label>搜索 ID<input name="search" maxLength={100} /></label>
      <label>ID 排序<select name="order"><option value="asc">升序</option><option value="desc">降序</option></select></label>
      <button>搜索</button>
    </form>
    <Paginated<CatalogEntry> key={kind + query} path={kind + (query ? '?' + query : '')}>{items => <Table
      headers={['ID', '名称', '来源']}
      rows={items.map(item => {
        const id = (kind === 'tools' ? item.tool_id : item.name) ?? '';
        return { key: id, cells: [
          <a href={link(kind, id)}>{id}</a>, item.label ?? item.name ?? id, item.source,
        ] };
      })} />}
    </Paginated>
  </>;
}

function SkillResources({ entry }: { entry: CatalogEntry }) {
  const [open, setOpen] = useState(false);
  return <>
    <Fields rows={[['来源', entry.configuration_source ?? entry.source], ['完整性通过', flag(entry.integrity)],
      ['依赖', entry.dependencies?.join('、') || '—']]} />
    <h3>资源文件</h3>
    <Table headers={['文件', '类型', '字节']} rows={(entry.resources ?? []).map(row =>
      ({ key: row.name, cells: [row.name, row.kind, row.size] }))} />
    <div className="actions"><button onClick={() => setOpen(!open)} disabled={!entry.resource_digest || entry.integrity !== 'yes'}>
      {open ? '收起' : '预览'} SKILL.md
    </button></div>
    {open && entry.resource_digest && <Resource<{ render_safe_markdown: string }>
      path={'skills/' + segment(entry.name ?? '') + '/document?resource_digest=' + segment(entry.resource_digest)}>
      {doc => <pre className="agent-preview">{doc.render_safe_markdown}</pre>}
    </Resource>}
  </>;
}

function InlineModelDetails({ model }: { model: Model }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [opened, setOpened] = useState(false);
  useEffect(() => {
    if (!opened) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [opened]);
  return <div className="agent-model-panel">
    <button className="agent-model-trigger" type="button" aria-haspopup="dialog" onClick={() => {
      setOpened(true);
      dialog.current?.showModal();
    }}>
      <span className="agent-model-title"><strong>{model.label || model.model_id}</strong><small>{model.model_id}</small></span>
      <span className="agent-model-status">{model.enabled ? '启用' : '停用'}</span>
      <span className="agent-expand-label">查看详情 →</span>
    </button>
    <dialog ref={dialog} className="agent-model-drawer" aria-labelledby={titleId} onClose={() => setOpened(false)}
      onClick={event => {
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.target === event.currentTarget && (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom)) event.currentTarget.close();
      }}>
      <div className="agent-drawer-heading">
        <div><h2 id={titleId}>{model.label || model.model_id}</h2><p>{model.provider_id} · {model.upstream_model_id}</p></div>
        <button type="button" aria-label="关闭模型详情" onClick={() => dialog.current?.close()}><X size={20} /></button>
      </div>
      <div className="agent-drawer-content">{opened && <ModelDetails item={model} id={model.model_id} />}</div>
    </dialog>
  </div>;
}

type ModelMetadata = {
  context_length_display?: string; notes: string[];
  description?: string; documentation_url?: string; source_url?: string;
  verified_at?: string; effective_from?: string; valid_until?: string;
  pricing: {
    label: string; currency: string; input_min_tokens?: number; input_max_tokens?: number;
    schedule?: string; input?: number; cache_read?: number; cache_write?: number; output?: number;
  }[];
};

function ModelPrices({ prices }: { prices: ModelMetadata['pricing'] }) {
  const memberLabels = new Set(prices.filter(price => price.label.endsWith(' · 会员价')).map(price => price.label.replace(' · 会员价', '')));
  return <div className="agent-price-list">{prices.filter(price =>
    !price.label.endsWith(' · 标准价') || !memberLabels.has(price.label.replace(' · 标准价', '')),
  ).map((price, index) => {
    const original = prices.find(row => row.label === price.label.replace(' · 会员价', ' · 标准价') &&
      row.input_min_tokens === price.input_min_tokens && row.input_max_tokens === price.input_max_tokens);
    const symbol = ({ CNY: '¥', USD: '$', EUR: '€', GBP: '£' } as Record<string, string>)[price.currency] ?? price.currency;
    const amount = (value: number) => symbol + value.toLocaleString('zh-CN', { maximumFractionDigits: 8 });
    return <div className="agent-price-card" key={index}>
      <h4>{price.label}</h4>
      {price.schedule && <p className="note">{price.schedule}</p>}
      {!!(price.input_min_tokens || price.input_max_tokens) && <p className="note">
        {price.input_min_tokens ?? 0} &lt; 输入 Token{price.input_max_tokens ? ' ≤ ' + price.input_max_tokens : ''}
      </p>}
      <dl>{([['input', '输入'], ['cache_read', '输入（缓存命中）'], ['cache_write', '缓存写入'], ['output', '输出']] as const)
        .filter(([key]) => price[key] != null).map(([key, label]) => <div key={key}>
          <dt>{label}</dt><dd><strong>{amount(price[key]!)} / M Token</strong>
            {original && original !== price && original[key] != null && <del>{amount(original[key]!)}</del>}
          </dd>
        </div>)}</dl>
    </div>;
  })}</div>;
}

function ExternalLink({ url, children }: { url?: string; children: ReactNode }) {
  if (!url || !/^https?:\/\//i.test(url)) return <span>—</span>;
  return <a href={url} target="_blank" rel="noopener noreferrer" className="agent-external-link">{children}<ExternalLinkIcon size={13} aria-hidden="true" /><span className="agent-sr-only">（在新标签页打开）</span></a>;
}

function ModelDetails({ item, id }: { item: CatalogEntry; id: string }) {
  const metadata = useResource<ModelMetadata>('/agent/model-metadata/' + segment(id));
  const caps = item.capabilities ?? {};
  const support = (value: unknown) => typeof value === 'boolean' ? value ? '支持' : '不支持' : UNKNOWN;
  const info = metadata.data;
  const stale = info?.valid_until && Date.parse(info.valid_until) < Date.now();
  return <>
    <Fields rows={[
      ['模型名称', item.label], ['内部 Model ID', item.model_id],
      ['Provider', item.provider_id && <a href={link('providers', item.provider_id)}>{item.provider_id}</a>],
      ['上游 Model ID', item.upstream_model_id], ['上下文长度', info?.context_length_display ?? caps.context_window_tokens],
      ['最大输出 Token', caps.max_output_tokens], ['Tool Calling', support(caps.tool_calling)],
      ['Reasoning', support(caps.reasoning)], ['流式输出', support(caps.streaming)],
      ['默认用途', item.default_purposes?.join('、') || '自动选择'], ['启用状态', item.enabled ? '启用' : '停用'],
    ]} />
    {item.description && <p>{item.description}</p>}
    {!!Object.keys(item.request_params ?? {}).length && <><h3>Registry 请求参数</h3><pre className="agent-preview">{JSON.stringify(item.request_params, null, 2)}</pre></>}
    <h3>模型介绍与文档</h3>
    {metadata.loading && <p role="status">正在读取模型资料…</p>}
    {metadata.error && <p className="error" role="alert">{metadata.error}</p>}
    {info?.description && <p>{info.description}</p>}
    {info?.documentation_url && <ExternalLink url={info.documentation_url}>查看官方文档</ExternalLink>}
    {info?.notes.map(note => <p className="note" key={note}>{note}</p>)}
    <h3>参考价格</h3>
    <p className="note">M = 10⁶ Token，价格仅供参考，实际费用以供应商账单为准。</p>
    <Fields rows={[
      ['数据来源', <ExternalLink url={info?.source_url}>查看价格来源</ExternalLink>],
      ['核验时间', info?.verified_at ? new Date(info.verified_at).toLocaleString('zh-CN') : '尚未核验'],
      ...(info?.effective_from ? [['生效时间', new Date(info.effective_from).toLocaleString('zh-CN')] as [string, ReactNode]] : []),
    ]} />
    {stale && <p role="status" className="error">价格资料已过有效期，请重新核验。</p>}
    {info?.pricing.length ? <ModelPrices prices={info.pricing} /> :
      <p>{info?.notes.length ? '请查看上述官网报价说明。' : '暂无已核验价格资料'}</p>}
    <details><summary>调用参数与预算</summary><Fields rows={Object.entries(caps)
      .filter(([key, value]) => ['temperature', 'thinking', 'stream_options', 'chat_max_tokens', 'agent_max_tokens'].includes(key) && value !== null && value !== undefined)
      .map(([key, value]) => [
        ({ chat: '对话', streaming: '流式输出', tool_calling: '工具调用', reasoning: '推理',
          temperature: '温度参数', thinking: '思考参数策略', stream_options: '流式用量参数',
          chat_max_tokens: '对话输出预算', agent_max_tokens: 'Agent 输出预算',
          max_output_tokens: '配置输出上限', context_window_tokens: '配置上下文上限',
        } as Record<string, string>)[key] ?? key,
        typeof value === 'boolean' ? support(value) : value === 'none' ? '默认' : value,
      ])} /></details>
  </>;
}

function CatalogDetail({ kind, id }: { kind: Catalog; id: string }) {
  return <><h2>{catalogNames[kind]} 详情</h2><a href={'#/agent/' + kind}>返回列表</a>
    <Resource<CatalogEntry> path={kind + '/' + segment(id)}>{item => <>
      <h3>{item.label ?? item.name ?? id}</h3>{item.description && <p>{item.description}</p>}
        {kind === 'providers' && <Fields rows={[['Provider ID', item.provider_id], ['协议', item.protocol], ['Base URL', item.base_url && <ExternalLink url={item.base_url}>{item.base_url}</ExternalLink>],
          ['凭据存在', item.credential_present ? '是' : '否'], ['配置启用', item.enabled ? '是' : '否'],
          ['关联模型', item.model_ids?.length ? <ul>{item.model_ids.map(model =>
            <li key={model}><a href={link('models', model)}>{model}</a></li>)}</ul> : '无']]} />}
        {kind === 'models' && <ModelDetails item={item} id={id} />}
      {kind === 'tools' && <>
        <Fields rows={[['Tool ID', item.tool_id], ['来源', item.source], ['注册类型', item.registration],
          ['可用条件', item.conditions?.join('、') || '—']]} />
        <h3>参数 Schema</h3>
        {item.parameters_schema ? <pre className="agent-preview">{JSON.stringify(item.parameters_schema, null, 2)}</pre> : <p>{UNKNOWN}</p>}
      </>}
      {kind === 'skills' && <SkillResources entry={item} />}
    </>}</Resource>
  </>;
}

const modules = [
  { id: 'providers', title: '模型与供应商', description: 'Provider / Model', icon: Layers },
  { id: 'tools', title: 'Tools', description: '工具目录', icon: Wrench },
  { id: 'skills', title: 'Skills', description: '技能目录', icon: BookOpen },
] as const;

export function AgentManagement({ route }: { route: string }) {
  const [, , section, encodedId, operationId, ...extra] = route.split('/');
  const catalog = Object.hasOwn(catalogNames, section) ? section as Catalog : undefined;
  const kind = catalog ?? 'providers';
  const activeModule = kind === 'models' ? 'providers' : kind;
  let id: string | undefined;
  let invalidId = false;
  if (catalog && encodedId) {
    try { id = decodeURIComponent(encodedId); }
    catch { invalidId = true; }
  }
  return <div className="agent-management">
    <div className="agent-heading">
      <h1><ShieldCheck aria-hidden="true" />深知 · Agent 目录</h1>
      <span>只读 · Agent API Registry 配置快照</span>
    </div>
    <nav className="agent-modules" aria-label="Agent 管理">
      {modules.map(({ id: module, title, description, icon: Icon }) =>
        <a key={module} href={'#/agent/' + module} aria-current={activeModule === module ? 'true' : undefined}>
          <Icon aria-hidden="true" size={24} />
          <strong>{title}</strong>
          <span>{description}</span>
        </a>)}
    </nav>
    {invalidId || operationId || extra.length || (section && !catalog) ? <p role="alert">无效的目录路径</p> :
      id ? <CatalogDetail key={route} kind={kind} id={id} /> :
        kind === 'tools' || kind === 'skills' ? <CatalogList key={kind} kind={kind} /> : <ProviderCatalog />}
  </div>;
}
