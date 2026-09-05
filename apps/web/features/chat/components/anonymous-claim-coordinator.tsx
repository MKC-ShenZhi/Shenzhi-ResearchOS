"use client";

import { useEffect, useRef } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { useAskSidebarBridge } from "@/stores/ask-sidebar-bridge";
import {
  ANONYMOUS_CLAIM_RETRY_DELAY_MS,
  anonymousClaimAttemptUser,
  claimAnonymousSessions,
  shouldRetryAnonymousClaim,
  shouldRefreshAfterAnonymousClaim,
} from "../services/anonymous-claim";

export function AnonymousClaimCoordinator() {
  const { session, isPending } = useAuth();
  const attemptedUserRef = useRef<string | null>(null);
  const attemptsRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bumpHistoryRefresh = useAskSidebarBridge((state) => state.bumpHistoryRefresh);
  const requestReset = useAskSidebarBridge((state) => state.requestReset);

  useEffect(() => {
    const userId = session?.user.id;
    const attemptUser = anonymousClaimAttemptUser(
      isPending,
      userId,
      attemptedUserRef.current,
    );
    if (!attemptUser) return;
    attemptedUserRef.current = attemptUser;
    attemptsRef.current = 0;
    let cancelled = false;
    const attempt = () => {
      if (cancelled || attemptedUserRef.current !== attemptUser) return;
      attemptsRef.current += 1;
      void claimAnonymousSessions()
        .then((result) => {
          if (cancelled || attemptedUserRef.current !== attemptUser) return;
          if (shouldRefreshAfterAnonymousClaim(result)) {
            requestReset();
            bumpHistoryRefresh();
          }
          if (shouldRetryAnonymousClaim(result, attemptsRef.current)) {
            retryTimerRef.current = setTimeout(attempt, ANONYMOUS_CLAIM_RETRY_DELAY_MS);
          }
        })
        .catch(() => {
          // A reload or later login safely retries; Chat and login stay usable.
        });
    };
    attempt();
    return () => {
      cancelled = true;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    };
  }, [bumpHistoryRefresh, isPending, requestReset, session?.user.id]);

  return null;
}
