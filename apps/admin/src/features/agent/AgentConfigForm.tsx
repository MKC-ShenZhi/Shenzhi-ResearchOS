import type { ReactNode } from 'react';

type Entry = Record<string, unknown>;
export type ConfigSpec = {
  schema_version: number; build_revision: string; runtime_version: string;
  providers: Entry[]; models: Entry[]; defaults: Record<string, string>;
  tools: (Entry & { id: string })[]; skills: (Entry & { id: string })[];
};

const booleanCapabilities = ['chat', 'streaming', 'tool_calling', 'reasoning', 'temperature', 'stream_options'];
const numericCapabilities = ['chat_max_tokens', 'agent_max_tokens', 'max_output_tokens', 'context_window_tokens'];

export function AgentConfigForm({ spec, change, disabled, initializing }: {
  spec: ConfigSpec; change: (value: ConfigSpec) => void; disabled: boolean; initializing: boolean;
}) {
  function update(group: 'providers' | 'models', index: number, key: string, value: unknown) {
    change({ ...spec, [group]: spec[group].map((item, position) => position === index ? { ...item, [key]: value } : item) });
  }
  function field(group: 'providers' | 'models', item: Entry, index: number, key: string, label: string): ReactNode {
    return <label key={key}>{label}<input value={String(item[key] ?? '')} required
      onChange={event => update(group, index, key, event.target.value)} /></label>;
  }
  return <fieldset disabled={disabled}>
    <legend>Provider / Model 配置候选</legend>
    {initializing && <><label>Build<input required value={spec.build_revision} onChange={event => change({ ...spec, build_revision: event.target.value })} /></label>
    <label>Runtime<input required value={spec.runtime_version} onChange={event => change({ ...spec, runtime_version: event.target.value })} /></label></>}
    <h3>Providers</h3>
    {spec.providers.map((item, index) => <article key={index}>
      {field('providers', item, index, 'provider_id', 'Provider ID')}
      {field('providers', item, index, 'base_url', 'HTTPS Base URL')}
      {field('providers', item, index, 'secret_ref', 'Secret Reference')}
      <label>协议<select value={String(item.protocol ?? 'openai_chat_completions')}
        onChange={event => update('providers', index, 'protocol', event.target.value)}><option>openai_chat_completions</option></select></label>
      <label><input type="checkbox" checked={item.enabled !== false} onChange={event => update('providers', index, 'enabled', event.target.checked)} />启用</label>
      <p>关联模型 {spec.models.filter(model => model.provider_id === item.provider_id).map(model => String(model.model_id)).join('、') || '无'}</p>
    </article>)}
    <button type="button" onClick={() => change({ ...spec, providers: [...spec.providers,
      { provider_id: '', protocol: 'openai_chat_completions', base_url: '', secret_ref: '', enabled: true }] })}>新增 Provider</button>
    <p>Secret Reference 使用部署环境中的凭据引用名。</p>
    <h3>Models</h3>
    {spec.models.map((item, index) => {
      const capabilities = (item.capabilities ?? {}) as Entry;
      const capability = (key: string, value: unknown) => update('models', index, 'capabilities', { ...capabilities, [key]: value });
      return <article key={index}>
        {field('models', item, index, 'model_id', '内部 Model ID')}
        {field('models', item, index, 'upstream_model_id', '上游 Model ID')}
        {field('models', item, index, 'label', '名称')}
        {field('models', item, index, 'brand', 'Brand')}
        <label>Provider<select required value={String(item.provider_id ?? '')} onChange={event => update('models', index, 'provider_id', event.target.value)}>
          <option value="">请选择</option>{spec.providers.map((provider, position) => <option key={position} value={String(provider.provider_id)}>{String(provider.provider_id)}</option>)}
        </select></label>
        <label><input type="checkbox" checked={item.enabled !== false} onChange={event => update('models', index, 'enabled', event.target.checked)} />启用</label>
        <label>Thinking 默认值<select value={item.thinking_enabled == null ? '' : String(item.thinking_enabled)}
          onChange={event => update('models', index, 'thinking_enabled', event.target.value === '' ? null : event.target.value === 'true')}>
          <option value="">沿用默认</option><option value="true">开启</option><option value="false">关闭</option></select></label>
        <details><summary>Capabilities</summary>
          {booleanCapabilities.map(key => <label key={key}><input type="checkbox" checked={capabilities[key] === true ||
              (capabilities[key] == null && ['chat', 'streaming', 'temperature'].includes(key))}
            onChange={event => capability(key, event.target.checked)} />{key}</label>)}
          <label>thinking<select value={String(capabilities.thinking ?? 'none')} onChange={event => capability('thinking', event.target.value)}>
            {['none', 'enable_thinking', 'thinking'].map(value => <option key={value}>{value}</option>)}
          </select></label>
          {numericCapabilities.map(key => <label key={key}>{key}<input type="number" min={1}
            value={capabilities[key] == null ? '' : String(capabilities[key])}
            onChange={event => capability(key, event.target.value === '' ? null : Number(event.target.value))} /></label>)}
        </details>
      </article>;
    })}
    <button type="button" onClick={() => change({ ...spec, models: [...spec.models,
      { model_id: '', provider_id: '', upstream_model_id: '', label: '', brand: 'platform', enabled: true,
        capabilities: { chat: true, streaming: true, tool_calling: false, temperature: true,
          chat_max_tokens: 4096, agent_max_tokens: 32768, max_output_tokens: 4096 } }] })}>新增 Model</button>
    <h3>默认用途</h3>
    {['chat', 'agent'].map(purpose => <label key={purpose}>{purpose}<select value={spec.defaults[purpose] ?? ''}
      onChange={event => {
        const defaults = { ...spec.defaults };
        if (event.target.value) defaults[purpose] = event.target.value;
        else delete defaults[purpose];
        change({ ...spec, defaults });
      }}><option value="">自动选择</option>{spec.models.map((model, index) => <option key={index} value={String(model.model_id)}>{String(model.model_id)}</option>)}</select></label>)}
  </fieldset>;
}
