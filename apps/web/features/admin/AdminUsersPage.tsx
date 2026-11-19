"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Users } from "lucide-react";
import { AppShell } from "@/components/common/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getAdminUsers, type AdminUser, type UsageWindow } from "@/clients/backend/admin";
import { useAuth } from "@/components/auth/auth-provider";

const count = (value: number) => value.toLocaleString("zh-CN");
const date = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN") : "—";
const statusLabel = (value: string) => ({ ready: "已分配", abnormal: "权益异常", pending_initialization: "待初始化" })[value] ?? value;

function Tokens({ windows, field }: { windows: UsageWindow[]; field: "limit" | "used" | "held" | "remaining" }) {
  const tokens = windows.filter(w => w.metric === "tokens");
  if (!tokens.length) return <>—</>;
  // Independent rules/windows are never added together into a fictitious quota.
  return <>{tokens.map(w => <div key={w.rule_id} className="whitespace-nowrap py-1">
    {count(w[field])}<span className="ml-1 text-xs text-faint">{w.rule_id}</span>
  </div>)}</>;
}

export function AdminUsersPage() {
  const { session, isPending, openLogin } = useAuth();
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [plan, setPlan] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["admin-users", session?.user.id, page, search, plan],
    queryFn: ({ signal }) => getAdminUsers({ page, search, plan_id: plan }, signal),
    retry: false,
    enabled: !isPending && !!session?.user.id,
  });
  const data = query.data;
  const selected: AdminUser | undefined = data?.items.find(user => user.user_id === selectedId);

  return <AppShell><div className="mx-auto max-w-[1500px] space-y-6 px-4 py-8 sm:px-8">
    <div className="flex items-center justify-between gap-4">
      <div><h1 className="flex items-center gap-2 text-2xl font-semibold text-ink"><Users />用户管理</h1>
        <p className="mt-2 text-sm text-ink-2">只读查看注册用户、套餐与 Token 权益</p></div>
      <Button variant="outline" disabled={query.isFetching || !session} onClick={() => void query.refetch()}><RefreshCw />刷新</Button>
    </div>
    {query.isError && <p role="alert" className="rounded-xl border border-line p-4 text-danger">{query.error.message}</p>}
    {!isPending && !session && <Button onClick={() => openLogin()}>登录后查看管理员权限</Button>}
    {data && <div className="grid gap-4 sm:grid-cols-3">{([
      ["注册用户总数", data.stats.total_users], ["Free 用户数", data.stats.free_users], ["权益异常用户数", data.stats.abnormal_users],
    ] as const).map(([label, value]) => <div key={label} className="rounded-2xl border border-line bg-card p-5">
      <p className="text-sm text-ink-2">{label}</p><p className="mt-2 text-3xl font-semibold text-ink">{count(value)}</p>
    </div>)}</div>}
    <form className="flex flex-wrap gap-3" onSubmit={e => { e.preventDefault(); setSearch(draft.trim()); setPage(1); setSelectedId(null); }}>
      <Input aria-label="搜索用户名或邮箱" placeholder="搜索用户名或邮箱" value={draft} onChange={e => setDraft(e.target.value)} className="max-w-sm" maxLength={255} />
      <select aria-label="套餐筛选" className="rounded-xl border border-line bg-card px-3 text-sm text-ink" value={plan}
        onChange={e => { setPlan(e.target.value); setPage(1); setSelectedId(null); }}>
        <option value="">全部套餐</option>{data?.plans.map(value => <option key={value} value={value}>{value}</option>)}
        <option value="__missing__">待初始化</option>
      </select><Button type="submit">搜索</Button>
    </form>
    {query.isFetching && <p role="status" className="text-sm text-ink-2">正在读取最新数据…</p>}
    {data && <>
      <p className="text-xs text-faint">近实时 · 更新时间 {date(data.updated_at)}。{data.usage_note}</p>
      <div className="overflow-x-auto rounded-2xl border border-line bg-card"><table className="w-full text-left text-sm text-ink">
        <caption className="sr-only">用户权益列表，多条 Token 规则分别显示</caption>
        <thead className="bg-chip text-ink-2"><tr>{["用户 ID", "邮箱", "昵称", "注册时间", "套餐 / 状态", "Token 限额", "已使用", "预留", "剩余", "详情"].map(label => <th key={label} scope="col" className="whitespace-nowrap px-4 py-3 font-medium">{label}</th>)}</tr></thead>
        <tbody>{data.items.map(user => <tr key={user.user_id} className="border-t border-line">
          <td className="max-w-40 break-all px-4 py-3 font-mono text-xs">{user.user_id}</td><td className="px-4 py-3">{user.email}</td>
          <td className="px-4 py-3">{user.name || "—"}</td><td className="whitespace-nowrap px-4 py-3">{date(user.created_at)}</td>
          <td className="px-4 py-3">{user.plan_id ?? "—"}<p className={user.entitlement_status === "ready" ? "text-xs text-faint" : "text-xs text-danger"}>{statusLabel(user.entitlement_status)}</p></td>
          {(["limit", "used", "held", "remaining"] as const).map(field => <td key={field} className="px-4 py-3"><Tokens windows={user.usage_windows} field={field} /></td>)}
          <td className="px-4 py-3"><Button variant="ghost" size="sm" onClick={() => setSelectedId(selectedId === user.user_id ? null : user.user_id)}>查看权益</Button></td>
        </tr>)}</tbody>
      </table>{!data.items.length && <p className="p-8 text-center text-ink-2">暂无匹配用户</p>}</div>
      <div className="flex items-center justify-between text-sm text-ink-2"><span>共 {count(data.total)} 人 · 第 {page} / {Math.max(1, Math.ceil(data.total / data.page_size))} 页</span>
        <div className="flex gap-2"><Button variant="outline" disabled={page <= 1 || query.isFetching} onClick={() => { setPage(page - 1); setSelectedId(null); }}>上一页</Button>
          <Button variant="outline" disabled={page * data.page_size >= data.total || query.isFetching} onClick={() => { setPage(page + 1); setSelectedId(null); }}>下一页</Button></div></div>
      {selected && <section aria-label="用户权益详情" className="space-y-3 rounded-2xl border border-line bg-card p-5">
        <div className="flex justify-between"><h2 className="font-semibold text-ink">{selected.name || selected.email} · 权益详情</h2><Button variant="ghost" size="sm" onClick={() => setSelectedId(null)}>收起</Button></div>
        <p className="break-all text-sm text-ink-2">Owner：user:{selected.user_id} · Policy：{selected.policy_revision ?? "待初始化"} · 启用：{selected.entitlement_enabled == null ? "未知" : selected.entitlement_enabled ? "是" : "否"}</p>
        {!selected.model_calls_enabled && <p className="text-sm text-danger">模型调用门禁尚未就绪：请核验 Policy 批准状态、风险配置与权益启用状态。</p>}
        {selected.usage_windows.map(w => <div key={w.rule_id} className="rounded-xl bg-chip p-4 text-sm text-ink-2">
          <p className="font-medium text-ink">{w.rule_id} · {w.metric} · {w.purpose}</p>
          <p>限额 {count(w.limit)} / 已用 {count(w.used)} / 预留 {count(w.held)} / 剩余 {count(w.remaining)}</p>
          <p>{w.window_type === "rolling" ? `滚动窗口：${w.duration_seconds} 秒` : `${date(w.window_start)} 至 ${date(w.window_end)}`} · {w.accounting_basis}</p>
          {w.capability_id && <p>能力：{w.capability_id}</p>}
        </div>)}
        {!selected.usage_windows.length && <p className="text-sm text-danger">权益尚未初始化或 Policy 不可用，不能据此认定用量为零。</p>}
      </section>}
    </>}
  </div></AppShell>;
}
