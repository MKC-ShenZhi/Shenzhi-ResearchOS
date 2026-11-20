import { Fragment, useState } from 'react';
import { api } from '../api';
import { useResource } from '../useResource';
import { AssignmentEditor } from './AssignmentEditor';
import type { Plan } from '../types';
export function PlansPage() {
 const q=useResource<{items:Plan[]}>('/plans');
 const [page,setPage]=useState<'preview'|'operations'>('preview');
 const [bundle,setBundle]=useState<Record<string,unknown>>(),[reason,setReason]=useState(''),[approval,setApproval]=useState(''),[riskApproval,setRiskApproval]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[operation,setOperation]=useState<string>(),[before,setBefore]=useState(''),[migration,setMigration]=useState<{id:string;email:string}[]>();
 return <><header><div><h1>套餐管理</h1><p>固定三档 · 暂时全部免费 · 上海自然日 · 输入＋输出 Token</p></div><button onClick={q.refresh}>刷新</button></header>{q.loading&&<p role="status">正在读取…</p>}{q.error&&<p role="alert" className="error">{q.error}</p>}<nav className="page-navigation" aria-label="套餐管理分页"><button type="button" aria-current={page==='preview'?'page':undefined} onClick={()=>setPage('preview')}>套餐预览</button><button type="button" aria-current={page==='operations'?'page':undefined} onClick={()=>setPage('operations')}>发布与迁移</button></nav>
 <div hidden={page!=='preview'}><div className="cards">{q.data?.items.map(p=><article key={p.plan_id}><h2>{p.name}</h2><strong>{p.daily_tokens.toLocaleString()} Token / 日</strong><p>Deep Research：{p.deep_research?'允许':'禁止'}</p><p>状态：{p.published?'已发布，可分配':'未发布'}</p><p>模型风险门禁：{p.model_risk_ready?'已配置批准引用':'未批准，模型调用将拒绝'}</p><code>{p.policy_revision??'尚无版本'}</code><details><summary>已发布能力（模型、通用 Tool / Skill）</summary>{p.capabilities.map(c=><p key={c}>{c}</p>)}</details></article>)}</div>
 </div>
 <div className="plan-operations" hidden={page!=='operations'}>
 <article><h2>发布套餐新版本</h2>
 <p>首次上线套餐，或套餐配置更新时，在这里发布 Basic、Pro、Research 三档的新版本。日常给用户分配已有套餐，请前往<a href="#/users">用户管理</a>。</p>
 <p>每次发布都会保存独立的规则版本（Policy），已发布版本不能修改。发布后，新版本可用于分配；已有用户仍使用原版本，需要在用户管理中另行切换。</p>
 <ol className="publish-steps"><li><strong>准备发布包</strong><p>使用部署流程生成的 JSON 文件，包含三档套餐的规则和能力配置。配置有变更时，请让部署维护人员生成新的版本。</p></li><li><strong>上传并核对</strong><p>选择文件后，核对下方显示的三个版本号。上传仅载入文件，点击“确认发布”才会提交。</p></li><li><strong>填写记录并发布</strong><p>说明发布原因，并填写审批记录的编号或链接，便于后续追溯。</p></li></ol><input aria-label="Policy 发布包" type="file" accept=".json" disabled={busy||!!operation} onChange={async e=>{try{const file=e.target.files?.[0];if(file){if(file.size>2000000)throw new Error('发布包不能超过 2 MB');const value=JSON.parse(await file.text());if(!Array.isArray(value.policies)||value.policies.length!==3)throw new Error('需要包含三档 policies 的发布包');setBundle(value);setMessage('发布包已载入，请核对版本与能力后确认。');}}catch(e){setMessage((e as Error).message);}}}/>{bundle&&<pre>{JSON.stringify((bundle.policies as {plan_id:string;policy_revision:string}[]).map(p=>({plan:p.plan_id,revision:p.policy_revision})),null,2)}</pre>}<div className="actions publish-fields"><label>发布原因（必填）<input aria-label="发布原因" placeholder="例如：更新可用模型配置" value={reason} disabled={!!operation} onChange={e=>setReason(e.target.value)} maxLength={255}/></label><label>套餐规则审批记录（必填）<input aria-label="Policy 审批引用" placeholder="审批记录编号或链接" value={approval} disabled={!!operation} onChange={e=>setApproval(e.target.value)} maxLength={255}/></label><label>模型风险审批记录（按发布包要求）<input aria-label="模型风险审批引用" placeholder="审批记录编号或链接" value={riskApproval} disabled={!!operation} onChange={e=>setRiskApproval(e.target.value)} maxLength={255}/></label><button disabled={busy||!bundle||!reason.trim()||!approval.trim()} onClick={async()=>{if(!window.confirm('确认发布 Basic、Pro、Research 的三个新版本？发布后可供分配，已有用户仍使用原版本。'))return;setBusy(true);const id=operation??crypto.randomUUID();setOperation(id);try{await api('/plans/publish',{method:'POST',body:JSON.stringify({...bundle,operation_id:id,reason,approval_ref:approval,risk_approval_ref:riskApproval||null})});setMessage('套餐新版本已发布。可在“套餐预览”中查看，并前往“用户管理”分配给用户。');setOperation(undefined);setBundle(undefined);q.refresh();}catch(e){setMessage((e as Error).message+'；重试沿用原操作 ID。');}finally{setBusy(false);}}}>{operation?'重试发布':'确认发布'}</button></div><p className="note">模型风险审批记录须与发布包中的风险配置配套；仅填写记录不会启用模型调用。发布包未包含已批准的模型风险配置时，发布后模型调用仍会被拒绝。</p></article>
 <article><h2>历史账号迁移预览</h2><p>用于给历史注册、尚未分配套餐的账号补充 Basic 基础版。先选择注册时间截止点，再预览名单；预览不会修改账号，后续需填写原因并确认执行。已有套餐或已停用的权益均保留，每批最多 100 人。</p><div className="actions"><input aria-label="历史账号截止时间" type="datetime-local" value={before} onChange={e=>setBefore(e.target.value)}/><button disabled={!before||busy} onClick={async()=>{setBusy(true);try{const r=await api<{items:{id:string;email:string}[]}>('/migration/preview',{method:'POST',body:JSON.stringify({before:new Date(before).toISOString(),limit:100})});setMigration(r.items);}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}}}>预览待迁移账号</button></div>{migration&&<p>本批 {migration.length} 人：{migration.map(u=>u.email).join('、')||'无符合条件账号'}</p>}</article>{migration&&migration.length>0&&<AssignmentEditor ids={migration.map(u=>u.id)} initializeOnly done={()=>setMigration(undefined)}/>}<p role="status">{message}</p></div></>;
}
function auditSummary(payload: unknown) {
 const record = (value: unknown): Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
 const data=record(payload), request=record(data.request);
 const ids=Array.isArray(request.user_ids) ? request.user_ids.filter((id): id is string => typeof id==='string' && !!id) : [];
 if (!ids.length && typeof data.owner_id==='string' && data.owner_id.startsWith('user:')) ids.push(data.owner_id.slice(5));
 const action=typeof data.action==='string' ? data.action : undefined;
 const labels:Record<string,string>={publish:'发布套餐',assign:'分配套餐',disable:'停用权益',restore:'恢复权益','reconcile-close':'对账关闭历史授权',revoke:'撤销授权'};
 const label=action ? labels[action]??action : '—';
 return {accounts:ids.join('、')||'—', action:request.preview===true ? `预览：${label}` : label};
}

export function AuditPage() {
 const [page,setPage]=useState(1);
 const [expandedId,setExpandedId]=useState<string>();
 const q=useResource<{items:{operation_id:string;principal:string;reason:string;created_at:string;payload:unknown;target_accounts?:{user_id:string;email:string|null}[]}[]}>('/audit?page='+page);
 return <>
  <header><h1>操作审计</h1><button onClick={q.refresh} disabled={q.loading}>刷新</button></header>
  {q.loading&&<p role="status">正在读取…</p>}
  {q.error&&<p role="alert" className="error">{q.error}</p>}
  {q.data&&<div className="table-wrap"><table className="audit-table" aria-label="操作审计记录">
   <thead><tr><th scope="col" className="audit-time">操作时间</th><th scope="col">被操作账户</th><th scope="col" className="audit-principal">操作人</th><th scope="col" className="audit-action">动作</th></tr></thead>
   <tbody>{q.data.items.map(i=>{
    const expanded=expandedId===i.operation_id;
    const summary=auditSummary(i.payload);
    const accounts=i.target_accounts?.length ? i.target_accounts.map(a=>a.email||a.user_id).join('、') : summary.accounts;
    return <Fragment key={i.operation_id}>
     <tr className={expanded?'audit-selected':undefined}>
      <td><time dateTime={i.created_at}>{new Date(i.created_at).toLocaleString('zh-CN',{hour12:false})}</time></td>
      <td><span className="audit-truncate" title={accounts}>{accounts}</span></td>
      <td><span className="audit-truncate" title={i.principal}>{i.principal}</span></td>
      <td><button type="button" aria-label={`${expanded?'收起':'展开'}${summary.action}记录 ${i.operation_id}`} aria-expanded={expanded} aria-controls={expanded?`audit-detail-${i.operation_id}`:undefined} onClick={()=>setExpandedId(expanded?undefined:i.operation_id)}>{summary.action}<span aria-hidden="true">{expanded?'▴':'▾'}</span></button></td>
     </tr>
     {expanded&&<tr id={`audit-detail-${i.operation_id}`} className="audit-detail"><td colSpan={4}>
      <p><strong>操作 ID：</strong><code>{i.operation_id}</code></p>
      <p><strong>被操作账户：</strong>{accounts}</p><p><strong>操作原因：</strong>{i.reason}</p>
      <pre>{JSON.stringify(i.payload,null,2)}</pre>
     </td></tr>}
    </Fragment>;
   })}
   {!q.data.items.length&&<tr><td colSpan={4} className="empty">暂无记录</td></tr>}</tbody>
  </table></div>}
  <footer><button disabled={page<=1||q.loading} onClick={()=>{setExpandedId(undefined);setPage(page-1);}}>上一页</button><span>第 {page} 页 · 每页 20 条{q.data&&` · 本页 ${q.data.items.length} 条`}</span><button disabled={q.loading||!q.data||q.data.items.length<20} onClick={()=>{setExpandedId(undefined);setPage(page+1);}}>下一页</button></footer>
 </>;
}
