import { useState } from 'react';
import { useResource } from '../useResource';
import type { AdminUsers, UsageWindow } from '../types';
const date = (s: string | null) => s ? new Date(s).toLocaleString('zh-CN') : '—';
const number = (n: number | null | undefined) => n == null ? '未知' : n.toLocaleString('zh-CN');
function Tokens({windows, field}: {windows: UsageWindow[], field: 'limit'|'used'|'held'|'remaining'}) {
  const rows = windows.filter(w => w.metric === 'tokens');
  return rows.length ? rows.map(w => <div key={w.rule_id}>{number(w[field])}<small>{w.rule_id}</small></div>) : <>—</>;
}
export function UsersPage({overview = false}: {overview?: boolean}) {
  const [draft,setDraft] = useState(''), [search,setSearch] = useState(''), [plan,setPlan] = useState(''), [page,setPage] = useState(1), [selected,setSelected] = useState<string>();
  const q = useResource<AdminUsers>('/users?' + new URLSearchParams({page:String(page),search,plan_id:plan}));
  const d=q.data, user=d?.items.find(u=>u.user_id===selected);
  return <><header><div><h1>{overview?'总览':'用户管理'}</h1><p>注册用户与权益 · 只读视图</p></div><button disabled={q.loading} onClick={q.refresh}>刷新</button></header>
    {q.loading && <p role="status">正在读取…</p>}{q.error && <p className="error" role="alert">{q.error}</p>}
    {d && <><div className="stats">{[['注册用户总数',d.stats.total_users],['Free 用户数',d.stats.free_users],['权益异常用户数',d.stats.abnormal_users]].map(([k,v])=><article key={k}><p>{k}</p><strong>{v}</strong></article>)}</div>
    {overview ? <article><h2>管理概况</h2><p>用户与能力目录均为只读。能力配置不代表完整授权。</p></article> : <>
    <form onSubmit={e=>{e.preventDefault();setSearch(draft.trim());setPage(1);setSelected(undefined);}}><input aria-label="搜索用户名或邮箱" placeholder="搜索用户名或邮箱" maxLength={255} value={draft} onChange={e=>setDraft(e.target.value)}/><select aria-label="套餐筛选" value={plan} onChange={e=>{setPlan(e.target.value);setPage(1);setSelected(undefined);}}><option value="">全部套餐</option>{d.plans.map(p=><option key={p}>{p}</option>)}<option value="__missing__">待初始化</option></select><button>搜索</button></form>
    <p className="note">近实时 · {date(d.updated_at)}。{d.usage_note} 多条规则分别展示，不合并限额。</p>
    <div className="table-wrap"><table><caption className="sr-only">注册用户及独立规则 Token 用量</caption><thead><tr>{['用户 ID','邮箱','昵称','注册时间','套餐 / 权益状态','Token 限额','已使用','预留','剩余','详情'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{d.items.map(u=><tr key={u.user_id}><td className="id">{u.user_id}</td><td>{u.email}</td><td>{u.name||'—'}</td><td>{date(u.created_at)}</td><td>{u.plan_id??'—'}<small>{{ready:'已分配',abnormal:'权益异常',pending_initialization:'待初始化'}[u.entitlement_status]??u.entitlement_status}</small></td>{(['limit','used','held','remaining'] as const).map(f=><td key={f}><Tokens windows={u.usage_windows} field={f}/></td>)}<td><button onClick={()=>setSelected(selected===u.user_id?undefined:u.user_id)}>查看权益</button></td></tr>)}</tbody></table>{!d.items.length&&<p className="empty">暂无匹配用户</p>}</div>
    <footer>共 {d.total} 人 · 第 {page} / {Math.max(1,Math.ceil(d.total/d.page_size))} 页 <span><button disabled={page<=1} onClick={()=>{setPage(page-1);setSelected(undefined);}}>上一页</button><button disabled={page*d.page_size>=d.total} onClick={()=>{setPage(page+1);setSelected(undefined);}}>下一页</button></span></footer>
    {user&&<article><header><h2>权益详情 · {user.email}</h2><button onClick={()=>setSelected(undefined)}>收起</button></header><p>Owner: user:{user.user_id} · Policy: {user.policy_revision??'待初始化'} · 启用: {user.entitlement_enabled==null?'未知':user.entitlement_enabled?'是':'否'}</p>{!user.model_calls_enabled&&<p className="error">模型调用门禁尚未就绪，请核验 Policy、风险配置与权益状态。</p>}{user.usage_windows.map(w=><section key={w.rule_id}><h3>{w.rule_id} · {w.metric} · {w.purpose}</h3><p>限额 {number(w.limit)} / 已用 {number(w.used)} / 预留 {number(w.held)} / 剩余 {number(w.remaining)}</p><p>{w.window_type==='rolling'?`滚动窗口 ${w.duration_seconds} 秒`:`${date(w.window_start)} 至 ${date(w.window_end)}`} · {w.accounting_basis} · {w.capability_id??'通用规则'}</p></section>)}{!user.usage_windows.length&&<p className="error">权益尚未初始化或 Policy 不可用，不能据此认定用量为零。</p>}</article>}
    </>}</>}
  </>;
}
