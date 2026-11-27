import { useState } from 'react';
import { api } from '../api';
import { useResource } from '../useResource';
import type { Plan } from '../types';
type Result = {items:{user_id:string;status:string;reason?:string;before?:unknown;after?:unknown}[];preview:boolean};
export function AssignmentEditor({ids,done,initializeOnly=false}:{ids:string[];done:(message:string)=>void;initializeOnly?:boolean}) {
 const plans=useResource<{items:Plan[]}>('/plans');
 const [plan,setPlan]=useState('basic'),[action,setAction]=useState('assign'),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Result>(),[pending,setPending]=useState<Record<string,unknown>>();
 const [duration,setDuration]=useState(''),[previewKey,setPreviewKey]=useState('');
 const selected=plans.data?.items.find(p=>p.plan_id===plan);
 const paid=action==='assign'&&plan!=='basic';
 const validDuration=!paid||(Number.isInteger(Number(duration))&&Number(duration)>=1&&Number(duration)<=12);
 const fields={reason:reason.trim(),action,user_ids:ids,plan_id:action==='assign'?plan:null,policy_revision:action==='assign'?selected?.policy_revision:null,duration_months:paid?Number(duration):null,initialize_only:initializeOnly};
 const currentKey=JSON.stringify(fields);
 async function submit(preview:boolean) {
  if(!pending&&(!ids.length||!reason.trim()||!validDuration))return;
  if(!preview&&!pending&&(!result?.preview||previewKey!==currentKey))return;
  if(!preview&&!window.confirm(`确认执行权益调整？Pro/Research 从执行生效时间重新计算，覆盖现有到期日，可能缩短已有权益，不叠加剩余时长。未关闭任务可能阻止切换。`))return;
  setBusy(true);setError('');
  const body=(!preview&&pending)||{operation_id:crypto.randomUUID(),...fields,preview};
  if(!preview)setPending(body);
  try { const r=await api<Result>('/entitlements/assign',{method:'POST',body:JSON.stringify(body)});setResult(r);setPreviewKey(preview?currentKey:'');if(!preview){setPending(undefined);done(JSON.stringify(r,null,2));} }
  catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <article><h2>{initializeOnly?'历史用户初始化 Basic':'套餐与权益调整'} · 已选 {ids.length} 人</h2><p>Basic 永久免费。Pro/Research 必选 1–12 个自然月，从执行生效时间覆盖到期日，可能缩短已有权益，不叠加剩余时长。预览日期以实际执行结果为准。停用权益只能显式恢复。升级/降级须先关闭并结算现有 Grant；停用立即禁止新调用，已启动调用继续结算。预览不修改权益。</p><div className="actions"><select aria-label="操作" value={action} disabled={busy||initializeOnly||!!pending} onChange={e=>{setAction(e.target.value);setResult(undefined);}}><option value="assign">分配套餐</option><option value="disable">停用权益</option><option value="restore">恢复权益</option></select>{action==='assign'&&<select aria-label="目标套餐" value={plan} disabled={busy||initializeOnly||!!pending} onChange={e=>{setPlan(e.target.value);setResult(undefined);}}>{plans.data?.items.map(p=><option key={p.plan_id} value={p.plan_id}>{p.name}{p.published?'':'（未发布）'}</option>)}</select>}{paid&&<select aria-label="赠予自然月数（必选）" value={duration} disabled={busy||!!pending} onChange={e=>{setDuration(e.target.value);setResult(undefined);}}><option value="">请选择赠予月数</option>{Array.from({length:12},(_,i)=><option key={i+1} value={i+1}>{i+1} 个自然月</option>)}</select>}<input aria-label="操作原因" placeholder="必填：操作原因" value={reason} maxLength={255} disabled={busy||!!pending} onChange={e=>{setReason(e.target.value);setResult(undefined);}}/><button disabled={busy||!!pending||!reason.trim()||!ids.length||!validDuration} onClick={()=>void submit(true)}>预览</button><button disabled={busy||(!pending&&(!reason.trim()||!ids.length||!validDuration||(action==='assign'&&!selected?.published)||!result?.preview||previewKey!==currentKey))} onClick={()=>void submit(false)}>{pending?'重试原操作':'确认执行'}</button></div>{plans.error&&<p role="alert" className="error">{plans.error}</p>}{error&&<p role="alert" className="error">{error}；重试会沿用原操作 ID。</p>}{result&&<div role="status"><p>{result.preview?'预览结果':'执行结果'}：成功/可执行 {result.items.filter(i=>i.status!=='failed').length}，失败 {result.items.filter(i=>i.status==='failed').length}</p>{result.items.map(i=><section key={i.user_id}><strong>{i.user_id} · {i.status}</strong><p>{i.reason==='ACTIVE_GRANTS_REQUIRE_DRAIN'?'存在未安全关闭的任务授权，暂不能切换套餐。即使任务已结束或取消，缺失用量等未决结算仍会阻止切换，需要先对账处理（ACTIVE_GRANTS_REQUIRE_DRAIN）。':i.reason}</p>{i.before!==undefined&&<pre>{JSON.stringify({原权益:i.before,目标权益:i.after},null,2)}</pre>}</section>)}</div>}</article>;
}
