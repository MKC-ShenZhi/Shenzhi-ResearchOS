"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Trash2 } from "lucide-react";
import type { SettingsLocale } from "@/clients/backend/settings";
import { authClient } from "@/components/auth/auth-client";
import { useAuth } from "@/components/auth/auth-provider";
import { getAuthErrorMessage, isAuthErrorCode, PASSWORD_POLICY_MESSAGE } from "@/components/auth/auth-errors";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, validatePasswordPolicy } from "@/lib/auth/policies/password";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { accountMessages } from "../i18n";
import { sendSetPasswordOtp, setPasswordWithOtp } from "../services/account-password";
import { deleteCurrentAccount } from "../services/account-deletion";
import { AccountSessions } from "./account-sessions";

export function AccountSection({ locale }: { locale: SettingsLocale }) {
  const t = accountMessages[locale];
  const { session, isPending, refetchSession, openLogin } = useAuth();
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const [newEmail, setNewEmail] = useState("");
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
  const activeUserIdRef = useRef<string | null>(null);

  useEffect(() => {
    activeUserIdRef.current = session?.user.id ?? null;
    return () => { activeUserIdRef.current = null; };
  }, [session?.user.id]);

  useEffect(() => {
    if (otpCooldown <= 0) return;
    const timer = window.setInterval(() => setOtpCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [otpCooldown]);

  if (isPending) {
    return <div className="mt-3 rounded-2xl bg-card p-6 text-sm text-muted shadow-card">{t.loading}</div>;
  }
  if (!session) {
    return (
      <div className="mt-3 rounded-2xl bg-card p-6 shadow-card">
        <p className="text-sm text-muted">{t.signInPrompt}</p>
        <Button className="mt-4" onClick={() => openLogin()}>{t.signIn}</Button>
      </div>
    );
  }

  const name = nameDraft ?? session.user.name ?? "";
  const userId = session.user.id;
  const hasPassword = Boolean((session.user as { hasPassword?: boolean }).hasPassword);
  const resetFeedback = () => { setMessage(null); setError(null); };

  const stillAuthenticatedAs = async (expectedUserId: string) => {
    const latest = await authClient.getSession();
    return latest.data?.user.id === expectedUserId;
  };

  const updateName = async (event: FormEvent) => {
    event.preventDefault();
    resetFeedback();
    if (!name.trim()) return setError(t.nicknameRequired);
    setBusy(true);
    const result = await authClient.updateUser({ name: name.trim() });
    if (activeUserIdRef.current !== userId) return;
    if (result.error) {
      setError(getAuthErrorMessage(result.error, "昵称更新失败", "profile"));
    } else {
      setNameDraft(name.trim());
      await refetchSession();
      setMessage(t.nicknameUpdated);
    }
    setBusy(false);
  };

  const updatePassword = async (event: FormEvent) => {
    event.preventDefault();
    resetFeedback();
    if (hasPassword && !currentPassword) return setError(t.currentPasswordRequired);
    if (!validatePasswordPolicy(newPassword).valid) return setError(PASSWORD_POLICY_MESSAGE);
    if (hasPassword && newPassword === currentPassword) return setError(t.samePassword);
    if (newPassword !== confirmPassword) return setError(t.passwordMismatch);
    setBusy(true);
    if (hasPassword) {
      const result = await authClient.changePassword({
        currentPassword,
        newPassword,
        revokeOtherSessions: true,
      });
      if (activeUserIdRef.current !== userId) return;
      if (result.error) {
        setError(getAuthErrorMessage(result.error, "密码修改失败，请检查当前密码", "change-password"));
      } else {
        setMessage(t.passwordChanged);
      }
    } else {
      if (!/^\d{6}$/.test(otp)) {
        setBusy(false);
        return setError(t.otpRequired);
      }
      const result = await setPasswordWithOtp(otp, newPassword);
      if (activeUserIdRef.current !== userId) return;
      if (!result.ok) {
        setError(result.message === "set_password_failed" ? t.setPasswordFailed : result.message);
      } else {
        setMessage(t.passwordSet);
        await refetchSession();
      }
    }
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setOtp("");
    setBusy(false);
  };

  const submitEmailChange = async (userId: string, normalizedEmail: string) => {
    resetFeedback();
    setBusy(true);
    if (!(await stillAuthenticatedAs(userId))) {
      setBusy(false);
      return setError(t.reauthAccountMismatch);
    }
    const result = await authClient.changeEmail({
      newEmail: normalizedEmail,
      callbackURL: "/settings?tab=profile",
    });
    if (activeUserIdRef.current !== userId) return;
    if (result.error) {
      if (
        isAuthErrorCode(result.error, "SENSITIVE_SESSION_REQUIRED") ||
        isAuthErrorCode(result.error, "UNAUTHORIZED")
      ) {
        openLogin({
          notice: t.reauthNotice,
          onSuccess: () => submitEmailChange(userId, normalizedEmail),
        });
      }
      setError(getAuthErrorMessage(result.error, "邮箱变更请求失败", "change-email"));
    } else {
      setNewEmail("");
      setMessage(t.emailChangeRequested);
    }
    setBusy(false);
  };

  const requestEmailChange = async (event: FormEvent) => {
    event.preventDefault();
    const normalizedEmail = newEmail.trim().toLowerCase();
    if (!normalizedEmail) return setError(t.newEmail);
    openLogin({
      notice: t.reauthEmailNotice,
      onSuccess: () => submitEmailChange(userId, normalizedEmail),
    });
  };

  const sendOtp = async () => {
    resetFeedback();
    setBusy(true);
    const result = await sendSetPasswordOtp();
    if (activeUserIdRef.current !== userId) return;
    if (!result.ok) {
      setError(result.message === "send_otp_failed" ? t.sendOtpFailed : result.message);
    } else {
      setOtpCooldown(60);
      setMessage(t.otpSent);
    }
    setBusy(false);
  };

  const removeAccount = async () => {
    resetFeedback();
    setBusy(true);
    if (!(await stillAuthenticatedAs(userId))) {
      setBusy(false);
      return setError(t.reauthAccountMismatch);
    }
    const result = await deleteCurrentAccount();
    if (activeUserIdRef.current !== userId) return;
    if (!result.ok) {
      if (result.status === 401 || result.status === 409) {
        setConfirmDelete(false);
        openLogin({ notice: t.reauthNotice, onSuccess: removeAccount });
      } else {
        setError(result.message);
      }
    }
    setBusy(false);
  };

  return (
    <div className="mt-3 space-y-5 rounded-2xl bg-card p-6 shadow-card">
      <form onSubmit={updateName} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1.5 text-[13px] text-ink-2">
            {t.email}
            <Input value={session.user.email} readOnly disabled />
          </label>
          <label className="space-y-1.5 text-[13px] text-ink-2">
            {t.nickname}
            <Input
              value={name}
              onChange={(event) => setNameDraft(event.target.value)}
              maxLength={80}
            />
          </label>
        </div>
        <Button type="submit" variant="outline" disabled={busy}>{t.saveNickname}</Button>
      </form>

      <form onSubmit={requestEmailChange} className="space-y-3 border-t border-line pt-5">
        <label className="space-y-1.5 text-[13px] text-ink-2">
          {t.newEmail}
          <Input
            type="email"
            autoComplete="email"
            value={newEmail}
            onChange={(event) => setNewEmail(event.target.value)}
          />
        </label>
        <p className="text-xs text-muted">{t.emailChangeHint}</p>
        <Button type="submit" variant="outline" disabled={busy}>{t.requestEmailChange}</Button>
      </form>

      <form onSubmit={updatePassword} className="space-y-4 border-t border-line pt-5">
        <p className="text-[13px] font-medium text-ink-2">{hasPassword ? t.changePassword : t.setPassword}</p>
        {hasPassword ? (
          <Input
            type="password"
            autoComplete="current-password"
            placeholder={t.currentPassword}
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        ) : (
          <div className="flex gap-2">
            <Input
              inputMode="numeric"
              maxLength={6}
              placeholder={t.otpPlaceholder}
              value={otp}
              onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))}
            />
            <Button
              type="button"
              variant="outline"
              disabled={busy || otpCooldown > 0}
              onClick={() => void sendOtp()}
            >
              {otpCooldown > 0 ? t.resendOtp(otpCooldown) : t.sendOtp}
            </Button>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            type="password"
            autoComplete="new-password"
            minLength={PASSWORD_MIN_LENGTH}
            maxLength={PASSWORD_MAX_LENGTH}
            placeholder={t.newPassword}
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
          <Input
            type="password"
            autoComplete="new-password"
            minLength={PASSWORD_MIN_LENGTH}
            maxLength={PASSWORD_MAX_LENGTH}
            placeholder={t.confirmPassword}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </div>
        <Button type="submit" variant="outline" disabled={busy}>
          {hasPassword ? t.changePassword : t.setPassword}
        </Button>
      </form>

      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      {message && <p role="status" className="text-xs text-muted">{message}</p>}

      <AccountSessions
        key={session.session.token}
        currentToken={session.session.token}
        currentUserId={userId}
        locale={locale}
      />

      <div className="border-t border-line pt-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-[13px] font-medium text-danger">{t.deleteTitle}</p>
            <p className="mt-1 text-xs text-muted">{t.deleteHint}</p>
          </div>
          <Button type="button" variant="outline" className="text-danger" onClick={() => setConfirmDelete(true)}>
            <Trash2 aria-hidden="true" />
            {t.deleteButton}
          </Button>
        </div>
        {confirmDelete && (
          <div role="alertdialog" aria-modal="true" className="mt-4 rounded-xl border border-danger/30 p-4">
            <p className="text-sm text-ink">{t.deleteConfirmPrompt}</p>
            <Input
              className="mt-3"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              autoComplete="off"
              placeholder={t.deleteConfirmPlaceholder}
            />
            <div className="mt-3 flex gap-2">
              <Button
                variant="outline"
                onClick={() => { setConfirmDelete(false); setDeleteConfirmation(""); }}
              >
                {t.cancel}
              </Button>
              <Button
                variant="danger"
                disabled={busy || deleteConfirmation !== t.deleteConfirmPhrase}
                onClick={() => {
                  setConfirmDelete(false);
                  openLogin({ notice: t.reauthNotice, onSuccess: removeAccount });
                }}
              >
                {t.deleteConfirm}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
