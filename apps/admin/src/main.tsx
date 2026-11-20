import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { LayoutDashboard, Users, Boxes, LogOut, ShieldCheck } from 'lucide-react';
import { api } from './api';
import { UsersPage } from './features/UsersPage';
import { CapabilitiesPage } from './features/CapabilitiesPage';
import './style.css';
function App() {
 const [username,setUsername]=useState<string>(),[pending,setPending]=useState(true),[error,setError]=useState(''),[busy,setBusy]=useState(false),[route,setRoute]=useState(location.hash);
 useEffect(()=>{const expired=()=>{setUsername(undefined);setError('会话已过期，请重新登录');};const change=()=>setRoute(location.hash);window.addEventListener('admin-session-expired',expired);window.addEventListener('hashchange',change);api<{username:string}>('/auth/me').then(d=>setUsername(d.username)).catch(e=>setError(e.message)).finally(()=>setPending(false));return()=>{window.removeEventListener('admin-session-expired',expired);window.removeEventListener('hashchange',change);};},[]);
 async function logout(){setBusy(true);setError('');try{await api('/auth/logout',{method:'POST'});setUsername(undefined);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 if(pending)return <div className="login" role="status">正在验证管理会话…</div>;
 if(!username)return <div className="login"><form onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);setBusy(true);setError('');try{const d=await api<{username:string}>('/auth/login',{method:'POST',body:JSON.stringify({username:f.get('username'),password:f.get('password')})});setUsername(d.username);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}><ShieldCheck size={36}/><h1>ShenZhi Admin</h1><p>独立管理控制台 · 本地账号登录</p><label>账号<input name="username" autoComplete="username" required maxLength={255}/></label><label>密码<input name="password" type="password" autoComplete="current-password" required maxLength={1024}/></label>{error&&<p role="alert" className="error">{error}</p>}<button disabled={busy}>{busy?'正在登录…':'登录控制台'}</button></form></div>;
 return <div className="shell"><aside><div className="brand"><ShieldCheck/>深知 <small>ADMIN CONSOLE</small></div><nav>{[['#/overview','总览',LayoutDashboard],['#/users','用户管理',Users],['#/capabilities','能力管理',Boxes]].map(([href,label,Icon])=>{const I=Icon as typeof Users;return <a key={String(href)} href={String(href)} aria-current={route===href?'page':undefined}><I size={18}/>{String(label)}</a>;})}</nav><div className="account"><span>{username}</span><button onClick={logout} disabled={busy}><LogOut size={16}/>退出</button></div></aside><main>{error&&<p className="error" role="alert">{error}</p>}{route==='#/capabilities'?<CapabilitiesPage/>:<UsersPage key={route} overview={route!=='#/users'}/>}</main></div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
