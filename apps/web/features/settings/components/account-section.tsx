"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Trash2 } from "lucide-react";
import { authClient } from "@/components/auth/auth-client";
import { useAuth } from "@/components/auth/auth-provider";
import { getAuthErrorMessage, isAuthErrorCode, PASSWORD_POLICY_MESSAGE } from "@/components/auth/auth-errors";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, validatePasswordPolicy } from "@/lib/auth/policies/password";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type ListedSession = NonNullable<Awaited<ReturnType<typeof authClient.listSessions>>["data"]>[number];

function Sessions({ currentToken }: { currentToken: string }) {
  const [sessions, setSessions] = useState<ListedSession[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setBusy(true);
    const result = await authClient.listSessions();
    if (result.error) setError(getAuthErrorMessage(result.error, "无法加载登录会话", "session"));
    else setSessions(result.data ?? []);
    setBusy(false);
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  const revokeOthers = async () => {
    setBusy(true);
    const result = await authClient.revokeOtherSessions();
    if (result.error) setError(getAuthErrorMessage(result.error, "无法退出其他会话", "session"));
    else await load();
    setBusy(false);
  };
  return <div className="border-t border-line pt-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-[13px] font-medium text-ink-2">登录会话</p><p className="mt-1 text-xs text-muted">Better Auth 管理的当前及其他登录会话。</p></div><Button type="button" size="sm" variant="outline" disabled={busy || !sessions.some((item) => item.token !== currentToken)} onClick={() => void revokeOthers()}>{busy ? "处理中…" : "退出其他会话"}</Button></div>
    {error && <p role="alert" className="mt-3 text-xs text-danger">{error}</p>}
    <ul className="mt-3 divide-y divide-line">{sessions.map((item) => <li key={item.id} className="flex gap-3 py-3 text-xs text-muted"><span className="rounded-lg bg-chip px-2 py-1">{item.token === currentToken ? "当前" : "其他"}</span><span>创建于 {new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.createdAt))}</span></li>)}</ul>
  </div>;
}

export function AccountSection() {
  const { session, isPending, refetchSession, deleteAccount, openLogin } = useAuth();
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [otpCooldown, setOtpCooldown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  useEffect(() => {
    if (otpCooldown <= 0) return;
    const timer = window.setInterval(() => setOtpCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [otpCooldown]);
  if (isPending) return <div className="mt-3 rounded-2xl bg-card p-6 text-sm text-muted shadow-card">正在加载账户…</div>;
  if (!session) return <div className="mt-3 rounded-2xl bg-card p-6 shadow-card"><p className="text-sm text-muted">请先登录后查看和管理账户信息。</p><Button className="mt-4" onClick={() => openLogin()}>登录</Button></div>;
  const name = nameDraft ?? session.user.name ?? "";
  const hasPassword = Boolean((session.user as { hasPassword?: boolean }).hasPassword);
  const resetFeedback = () => { setMessage(null); setError(null); };
  const updateName = async (event: FormEvent) => {
    event.preventDefault(); resetFeedback();
    if (!name.trim()) return setError("请输入昵称");
    setBusy(true);
    const result = await authClient.updateUser({ name: name.trim() });
    if (result.error) setError(getAuthErrorMessage(result.error, "昵称更新失败", "profile"));
    else { setNameDraft(name.trim()); await refetchSession(); setMessage("昵称已更新"); }
    setBusy(false);
  };
  const updatePassword = async (event: FormEvent) => {
    event.preventDefault(); resetFeedback();
    if (hasPassword && !currentPassword) return setError("请输入当前密码");
    if (!validatePasswordPolicy(newPassword).valid) return setError(PASSWORD_POLICY_MESSAGE);
    if (newPassword !== confirmPassword) return setError("两次输入的密码不一致");
    setBusy(true);
    if (hasPassword) {
      const result = await authClient.changePassword({ currentPassword, newPassword, revokeOtherSessions: true });
      if (result.error) setError(getAuthErrorMessage(result.error, "密码修改失败，请检查当前密码", "change-password"));
      else setMessage("密码已修改，其他登录会话已退出");
    } else {
      if (!/^\d{6}$/.test(otp)) { setBusy(false); return setError("请输入 6 位数字验证码"); }
      const response = await fetch("/api/auth/password/set", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ otp, newPassword }) });
      const data = await response.json() as { message?: string };
      if (!response.ok) setError(data.message ?? "设置密码失败"); else { setMessage("密码已设置"); await refetchSession(); }
    }
    setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); setOtp(""); setBusy(false);
  };
  const sendOtp = async () => {
    resetFeedback(); setBusy(true);
    const response = await fetch("/api/auth/password/send-otp", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await response.json() as { message?: string };
    if (!response.ok) setError(data.message ?? "验证码发送失败");
    else { setOtpCooldown(60); setMessage("验证码已发送，请查收邮件"); }
    setBusy(false);
  };
  const removeAccount = async () => {
    resetFeedback(); setBusy(true);
    const result = await deleteAccount({});
    if (result.error) {
      if (isAuthErrorCode(result.error, "SESSION_EXPIRED") || isAuthErrorCode(result.error, "UNAUTHORIZED")) {
        setConfirmDelete(false);
        openLogin({ notice: "为保障账户安全，请重新登录后继续注销账号", onSuccess: removeAccount });
      } else setError(getAuthErrorMessage(result.error, "账号注销失败，请稍后重试", "delete-user"));
    }
    setBusy(false);
  };

  return <div className="mt-3 space-y-5 rounded-2xl bg-card p-6 shadow-card">
    <form onSubmit={updateName} className="space-y-4"><div className="grid gap-4 sm:grid-cols-2"><label className="space-y-1.5 text-[13px] text-ink-2">邮箱<Input value={session.user.email} readOnly disabled /></label><label className="space-y-1.5 text-[13px] text-ink-2">昵称<Input value={name} onChange={(event) => setNameDraft(event.target.value)} maxLength={80} /></label></div><Button type="submit" variant="outline" disabled={busy}>保存昵称</Button></form>
    <form onSubmit={updatePassword} className="space-y-4 border-t border-line pt-5"><p className="text-[13px] font-medium text-ink-2">{hasPassword ? "修改密码" : "设置密码"}</p>{hasPassword ? <Input type="password" autoComplete="current-password" placeholder="当前密码" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /> : <div className="flex gap-2"><Input inputMode="numeric" maxLength={6} placeholder="邮箱验证码" value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} /><Button type="button" variant="outline" disabled={busy || otpCooldown > 0} onClick={() => void sendOtp()}>{otpCooldown > 0 ? `${otpCooldown}s 后重发` : "获取验证码"}</Button></div>}<div className="grid gap-4 sm:grid-cols-2"><Input type="password" autoComplete="new-password" minLength={PASSWORD_MIN_LENGTH} maxLength={PASSWORD_MAX_LENGTH} placeholder="新密码" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /><Input type="password" autoComplete="new-password" minLength={PASSWORD_MIN_LENGTH} maxLength={PASSWORD_MAX_LENGTH} placeholder="确认新密码" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></div><Button type="submit" variant="outline" disabled={busy}>{hasPassword ? "修改密码" : "设置密码"}</Button></form>
    {error && <p role="alert" className="text-xs text-danger">{error}</p>}{message && <p role="status" className="text-xs text-muted">{message}</p>}
    <Sessions currentToken={session.session.token} />
    <div className="border-t border-line pt-5"><div className="flex items-center justify-between gap-4"><div><p className="text-[13px] font-medium text-danger">注销账号</p><p className="mt-1 text-xs text-muted">永久删除当前账号，无法撤销。</p></div><Button type="button" variant="outline" className="text-danger" onClick={() => setConfirmDelete(true)}><Trash2 aria-hidden="true" />注销账号</Button></div>{confirmDelete && <div role="alertdialog" aria-modal="true" className="mt-4 rounded-xl border border-danger/30 p-4"><p className="text-sm text-ink">请输入“注销账号”完成二次确认。</p><Input className="mt-3" value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} autoComplete="off" placeholder="注销账号" /><div className="mt-3 flex gap-2"><Button variant="outline" onClick={() => { setConfirmDelete(false); setDeleteConfirmation(""); }}>取消</Button><Button variant="danger" disabled={busy || deleteConfirmation !== "注销账号"} onClick={() => void removeAccount()}>确认注销</Button></div></div>}</div>
  </div>;
}
