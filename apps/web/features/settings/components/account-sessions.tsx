"use client";

import { useEffect, useRef, useState } from "react";
import { authClient } from "@/components/auth/auth-client";
import { useAuth } from "@/components/auth/auth-provider";
import {
  getAuthErrorMessage,
  isAuthErrorCode,
} from "@/components/auth/auth-errors";
import type { SettingsLocale } from "@/clients/settings";
import { Button } from "@/components/ui/button";
import { accountMessages } from "../i18n";

type ListedSession = NonNullable<Awaited<ReturnType<typeof authClient.listSessions>>["data"]>[number];

export function AccountSessions({
  currentToken,
  currentUserId,
  locale,
}: {
  currentToken: string;
  currentUserId: string;
  locale: SettingsLocale;
}) {
  const t = accountMessages[locale];
  const { openLogin } = useAuth();
  const [sessionList, setSessionList] = useState<{ token: string; items: ListedSession[] } | null>(null);
  const [busy, setBusy] = useState<"load" | "revoke" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeScopeRef = useRef<object | null>(null);
  const pendingRef = useRef(false);
  const sessions = sessionList?.token === currentToken ? sessionList.items : [];
  const dateLocale = locale === "en" ? "en-US" : "zh-CN";

  // Identity changes/unmounts invalidate pending requests and login callbacks.
  // Token rotation keeps this instance alive so reauthentication can resume.
  useEffect(() => {
    const scope = {};
    activeScopeRef.current = scope;
    pendingRef.current = false;
    return () => { activeScopeRef.current = null; };
  }, [currentUserId]);

  async function run(action: "load" | "revoke", reauthenticated = false): Promise<void> {
    const scope = activeScopeRef.current;
    if (!scope || pendingRef.current) return;
    const isActive = () => activeScopeRef.current === scope;
    const fallback = action === "load" ? t.sessionsLoadFailed : t.sessionsRevokeFailed;
    pendingRef.current = true;
    setBusy(action);
    setError(null);
    try {
      let token = currentToken;
      if (reauthenticated) {
        const latest = await authClient.getSession();
        if (!isActive()) return;
        if (latest.data?.user.id !== currentUserId) {
          setSessionList(null);
          setError(t.reauthAccountMismatch);
          return;
        }
        token = latest.data.session.token;
      }

      const handleError = (authError: unknown, message: string, retryAction: "load" | "revoke") => {
        setSessionList(null);
        if (isAuthErrorCode(authError, "SESSION_NOT_FRESH")) {
          setError(t.sessionsReauthRequired);
          if (!reauthenticated) {
            openLogin({
              notice: t.sessionsReauthNotice,
              onSuccess: async () => {
                if (isActive()) await run(retryAction, true);
              },
            });
          }
        } else {
          // Real authentication failures still flow through authClient's global
          // invalid-session event and AuthProvider's session refresh.
          setError(getAuthErrorMessage(authError, message, "session"));
        }
      };

      if (action === "revoke") {
        const result = await authClient.revokeOtherSessions();
        if (!isActive()) return;
        if (result.error) {
          handleError(result.error, t.sessionsRevokeFailed, "revoke");
          return;
        }
      }

      const result = await authClient.listSessions();
      if (!isActive()) return;
      if (result.error) {
        handleError(result.error, t.sessionsLoadFailed, "load");
      } else {
        setSessionList({ token, items: result.data ?? [] });
      }
    } catch {
      if (isActive()) {
        setSessionList(null);
        setError(fallback);
      }
    } finally {
      if (isActive()) {
        pendingRef.current = false;
        setBusy(null);
      }
    }
  }

  return (
    <div className="border-t border-line pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium text-ink-2">{t.sessionsTitle}</p>
          <p className="mt-1 text-xs text-muted">{t.sessionsHint}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy !== null}
            onClick={() => void run("load")}
          >
            {busy === "load" ? t.sessionsLoading : t.viewSessions}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy !== null || !sessions.some((item) => item.token !== currentToken)}
            onClick={() => void run("revoke")}
          >
            {busy === "revoke" ? t.revokeOthersBusy : t.revokeOthers}
          </Button>
        </div>
      </div>
      {error && <p role="alert" className="mt-3 text-xs text-danger">{error}</p>}
      <ul className="mt-3 divide-y divide-line">
        {sessions.map((item) => (
          <li key={item.id} className="flex gap-3 py-3 text-xs text-muted">
            <span className="rounded-lg bg-chip px-2 py-1">
              {item.token === currentToken ? t.sessionCurrent : t.sessionOther}
            </span>
            <span>
              {t.sessionCreated(new Intl.DateTimeFormat(dateLocale, {
                dateStyle: "medium",
                timeStyle: "short",
              }).format(new Date(item.createdAt)))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
