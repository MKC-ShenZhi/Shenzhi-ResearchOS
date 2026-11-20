import { useState } from 'react';
import { api } from '../api';
import { useResource } from '../useResource';
import type { Plan } from '../types';
type Result = {items:{user_id:string;status:string;reason?:string;before?:unknown;after?:unknown}[];preview:boolean};
export function AssignmentEditor({ids,done,initializeOnly=false}:{ids:string[];done:(message:string)=>void;initializeOnly?:boolean}) {
 const plans=useResource<{items:Plan[]}>('/plans');
 const [plan,setPlan]=useState('basic'),[action,setAction]=useState('assign'),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Result>(),[pending,setPending]=useState<Record<string,unknown>>();
 const selected=plans.data?.items.find(p=>p.plan_id===plan);
 async function submit(preview:boolean) {
  if(!ids.length||!reason.trim())return;
  if(!preview&&!window.confirm(`确认对 ${ids.length} 位用户执行${action==='assign'?`分配 ${plan}`:action==='disable'?'停用':'恢复'}？未关闭的任务可能阻止切换。`))return;
  setBusy(true);setError('');
  const body=(!preview&&pending)||{operation_id:crypto.randomUUID(),reason:reason.trim(),action,user_ids:ids,plan_id:action==='assign'?plan:null,policy_revision:action==='assign'?selected?.policy_revision:null,initialize_only:initializeOnly,preview};
  if(!preview)setPending(body);
  try { const r=await api<Result>('/entitlements/assign',{method:'POST',body:JSON.stringify(body)});setResult(r);if(!preview){setPending(undefined);done(JSON.stringify(r,null,2));} }
  catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <article><h2>{initializeOnly?'历史用户初始化 Basic':'套餐与权益调整'} · 已选 {ids.length} 人</h2><p>升级/降级须先关闭并结算现有 Grant；停用立即禁止新调用，已启动调用继续结算。预览不修改权益。</p><div className="actions"><select aria-label="操作" value={action} disabled={busy||initializeOnly||!!pending} onChange={e=>{setAction(e.target.value);setResult(undefined);}}><option value="assign">分配套餐</option><option value="disable">停用权益</option><option value="restore">恢复权益</option></select>{action==='assign'&&<select aria-label="目标套餐" value={plan} disabled={busy||initializeOnly||!!pending} onChange={e=>{setPlan(e.target.value);setResult(undefined);}}>{plans.data?.items.map(p=><option key={p.plan_id} value={p.plan_id}>{p.name}{p.published?'':'（未发布）'}</option>)}</select>}<input aria-label="操作原因" placeholder="必填：操作原因" value={reason} maxLength={255} disabled={busy||!!pending} onChange={e=>{setReason(e.target.value);setResult(undefined);}}/><button disabled={busy||!!pending||!reason.trim()||!ids.length} onClick={()=>void submit(true)}>预览</button><button disabled={busy||!reason.trim()||!ids.length||(action==='assign'&&!selected?.published)||(!pending&&!result?.preview)} onClick={()=>void submit(false)}>{pending?'重试原操作':'确认执行'}</button></div>{plans.error&&<p role="alert" className="error">{plans.error}</p>}{error&&<p role="alert" className="error">{error}；重试会沿用原操作 ID。</p>}{result&&<div role="status"><p>{result.preview?'预览结果':'执行结果'}：成功/可执行 {result.items.filter(i=>i.status!=='failed').length}，失败 {result.items.filter(i=>i.status==='failed').length}</p>{result.items.map(i=><section key={i.user_id}><strong>{i.user_id} · {i.status}</strong><p>{i.reason}</p>{i.before!==undefined&&<pre>{JSON.stringify({原权益:i.before,目标权益:i.after},null,2)}</pre>}</section>)}</div>}</article>;
}
