import { useLayoutEffect, useRef, useState } from 'react';
import { useResource } from '../useResource';

type Config = {models:{value:string;label:string;provider?:string;enabled:boolean}[];skills:{name:string;description?:string}[];default_model:string|null;source:string};

function SkillDescription({ description }: { description: string }) {
 const text = useRef<HTMLParagraphElement>(null);
 const [expanded, setExpanded] = useState(false);
 const [overflowing, setOverflowing] = useState(false);

 useLayoutEffect(() => {
  const element = text.current;
  if (!element || expanded) return;
  const measure = () => setOverflowing(element.scrollWidth > element.clientWidth);
  measure();
  const observer = new ResizeObserver(measure);
  observer.observe(element);
  return () => observer.disconnect();
 }, [description, expanded]);

 return <div className="capability-description">
  <p ref={text} className={expanded ? 'is-expanded' : undefined}>{description}</p>
  {(overflowing || expanded) && <button type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? '收起描述' : '展开描述'}</button>}
 </div>;
}

export function CapabilitiesPage() {
 const q=useResource<Config>('/capabilities');
 return <>
  <header><div><h1>能力管理</h1><p>当前运行配置的只读视图，不等同于完整的能力授权管理。</p></div><button onClick={q.refresh} disabled={q.loading}>刷新</button></header>
  {q.loading&&<p role="status">正在读取 Agent 配置…</p>}
  {q.error&&<p className="error" role="alert">{q.error}</p>}
  {q.data&&<>
   <p className="note">来源：{q.data.source} · 默认模型：{q.data.default_model??'未提供'}</p>
   <h2>Model · 模型</h2>
   <div className="capability-list">{q.data.models.map(m=><article className="capability-row" key={m.value}>
    <div className="capability-identity"><small>MODEL</small><h3>{m.label}</h3><code>{m.value}</code></div>
    <div className="capability-meta"><span>状态：{m.enabled?'启用':'未启用'}</span><span>Provider：{m.provider??'未提供'}</span></div>
   </article>)}</div>
   {!q.data.models.length&&<p>当前未暴露模型</p>}
   <h2>Skill · 技能</h2>
   <div className="capability-list">{q.data.skills.map(s=><article className="capability-row capability-skill" key={s.name}>
    <div className="capability-heading"><div className="capability-identity"><small>SKILL</small><h3>{s.name}</h3></div><span className="capability-meta">状态：当前配置已暴露</span></div>
    <SkillDescription description={s.description||'未提供描述'}/>
   </article>)}</div>
   {!q.data.skills.length&&<p>当前未暴露技能</p>}
  </>}
  <h2>Tool · 工具</h2><article><h3>目录尚未接入</h3><p>当前配置接口没有统一 Tool 目录来源。</p></article>
 </>;
}
