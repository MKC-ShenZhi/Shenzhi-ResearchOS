"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { useAskSidebarBridge } from "@/stores/ask-sidebar-bridge";
import {
  ANONYMOUS_CLAIM_RETRY_DELAY_MS,
  claimAnonymousSessions,
  previewAnonymousSessions,
  shouldRetryAnonymousClaim,
  shouldRefreshAfterAnonymousClaim,
} from "../services/anonymous-claim";

export function AnonymousClaimCoordinator() {
  const { session, isPending } = useAuth();
  // Remount on account changes so consent never carries across accounts.
  if (isPending || !session?.user.id) return null;
  return <ClaimPrompt key={session.user.id} account={session.user.email || session.user.name || "当前账号"} />;
}

function ClaimPrompt({ account }: { account: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const alive = useRef(false);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlight = useRef(false);
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const bumpHistoryRefresh = useAskSidebarBridge((state) => state.bumpHistoryRefresh);
  const requestReset = useAskSidebarBridge((state) => state.requestReset);

  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    void previewAnonymousSessions(controller.signal).then((available) => {
      if (controller.signal.aborted || available <= 0) return;
      setCount(available);
      dialog.current?.showModal();
    }).catch(() => { /* A failed preview must never trigger a migration. */ });
    return () => {
      alive.current = false;
      controller.abort();
      if (retryTimer.current !== null) clearTimeout(retryTimer.current);
    };
  }, []);

  const dismiss = () => {
    if (inFlight.current) return;
    dialog.current?.close();
  };

  const migrate = () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setNotice("");
    let attempts = 0;
    const attempt = async () => {
      if (!alive.current) return;
      attempts += 1;
      try {
        const result = await claimAnonymousSessions();
        if (!alive.current) return;
        if (shouldRefreshAfterAnonymousClaim(result)) {
          requestReset();
          bumpHistoryRefresh();
        }
        if (shouldRetryAnonymousClaim(result, attempts)) {
          retryTimer.current = setTimeout(() => void attempt(), ANONYMOUS_CLAIM_RETRY_DELAY_MS);
          return;
        }
        if (!result.durable) {
          setNotice("当前历史服务暂不支持迁移，请稍后再试。");
        } else if (result.skipped_streaming_count > 0) {
          setNotice("部分对话仍在生成，已完成的对话已迁移。请稍后点击重试。");
        } else {
          dialog.current?.close();
        }
      } catch {
        if (!alive.current) return;
        setNotice("迁移暂未完成，请稍后重试。已迁移的对话不会重复添加。");
      }
      inFlight.current = false;
      setBusy(false);
    };
    void attempt();
  };

  return (
    <dialog ref={dialog} aria-labelledby="claim-title" aria-describedby="claim-description"
      onCancel={(event) => { event.preventDefault(); dismiss(); }}
      className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border border-line bg-card p-6 text-ink shadow-xl backdrop:bg-black/40">
      <h2 id="claim-title" className="text-lg font-semibold">迁移对话历史？</h2>
      <p id="claim-description" className="mt-3 text-sm leading-6 text-muted">
        发现此浏览器中有 {count} 条未登录时的对话，是否将它们保存到当前账号？
      </p>
      <p className="mt-2 break-all rounded-lg bg-primary-soft px-3 py-2 text-sm">{account}</p>
      <p className="mt-3 text-xs leading-5 text-muted">选择暂不迁移不会删除这些对话，它们仍受匿名历史有效期限制。</p>
      {notice && <p role="status" className="mt-3 text-sm text-muted">{notice}</p>}
      <div className="mt-6 flex justify-end gap-3">
        <button type="button" autoFocus disabled={busy} onClick={dismiss}
          className="rounded-lg border border-line px-4 py-2 text-sm disabled:opacity-50">暂不迁移</button>
        <button type="button" disabled={busy} onClick={migrate}
          className="rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-deep disabled:opacity-50">
          {busy ? "正在迁移…" : notice ? "重试迁移" : "迁移到当前账号"}
        </button>
      </div>
    </dialog>
  );
}
