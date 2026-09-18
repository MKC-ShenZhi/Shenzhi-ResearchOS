"use client";

import { useCallback, useEffect, useState } from "react";
import { authClient } from "@/components/auth/auth-client";
import { useAuth } from "@/components/auth/auth-provider";
import {
  getAuthErrorMessage,
  isAuthErrorCode,
} from "@/components/auth/auth-errors";
import type { SettingsLocale } from "@/clients/backend/settings";
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
  const [sessions, setSessions] = useState<ListedSession[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dateLocale = locale === "en" ? "en-US" : "zh-CN";

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const result = await authClient.listSessions();
      if (result.error) {
        if (isAuthErrorCode(result.error, "SESSION_NOT_FRESH")) {
          setError(t.sessionsReauthRequired);
          openLogin({
            notice: t.sessionsReauthNotice,
            onSuccess: async () => {
              setBusy(true);
              try {
                const latest = await authClient.getSession();
                if (latest.data?.user.id !== currentUserId) {
                  setError(t.reauthAccountMismatch);
                  return;
                }

                const retry = await authClient.listSessions();
                if (retry.error) {
                  setError(getAuthErrorMessage(retry.error, t.sessionsLoadFailed, "session"));
                  return;
                }
                setSessions(retry.data ?? []);
                setError(null);
              } catch {
                setError(t.sessionsLoadFailed);
              } finally {
                setBusy(false);
              }
            },
          });
        } else {
          setError(getAuthErrorMessage(result.error, t.sessionsLoadFailed, "session"));
        }
      } else {
        setSessions(result.data ?? []);
        setError(null);
      }
    } catch {
      setError(t.sessionsLoadFailed);
    } finally {
      setBusy(false);
    }
  }, [currentUserId, openLogin, t]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function revokeOthers(): Promise<void> {
    setBusy(true);
    try {
      const result = await authClient.revokeOtherSessions();
      if (result.error) {
        if (isAuthErrorCode(result.error, "SESSION_NOT_FRESH")) {
          setError(t.sessionsReauthRequired);
          openLogin({
            notice: t.sessionsReauthNotice,
            onSuccess: async () => {
              setBusy(true);
              try {
                const latest = await authClient.getSession();
                if (latest.data?.user.id !== currentUserId) {
                  setError(t.reauthAccountMismatch);
                  return;
                }
                await revokeOthers();
              } catch {
                setError(t.sessionsRevokeFailed);
              } finally {
                setBusy(false);
              }
            },
          });
        } else {
          setError(getAuthErrorMessage(result.error, t.sessionsRevokeFailed, "session"));
        }
      } else {
        await load();
      }
    } catch {
      setError(t.sessionsRevokeFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-t border-line pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium text-ink-2">{t.sessionsTitle}</p>
          <p className="mt-1 text-xs text-muted">{t.sessionsHint}</p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy || !sessions.some((item) => item.token !== currentToken)}
          onClick={() => void revokeOthers()}
        >
          {busy ? t.revokeOthersBusy : t.revokeOthers}
        </Button>
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
