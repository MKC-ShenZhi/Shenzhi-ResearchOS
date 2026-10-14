"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { searchRestoration } from "@/lib/navigation/search-restoration";
import { useCurrentInternalPath } from "./use-current-internal-path";

function useSearchRestorationScope() {
  const { session, isPending } = useAuth();
  return isPending ? null : session?.user.id ? `user:${session.user.id}` : "anonymous";
}

/** Call once inside the application shell, under Suspense for useSearchParams. */
export function useRecordSearchRestoration() {
  const href = useCurrentInternalPath();
  const scope = useSearchRestorationScope();
  useEffect(() => {
    if (scope) searchRestoration.record(scope, href);
  }, [scope, href]);
}

export function useSearchRestorationHref(href: string) {
  const scope = useSearchRestorationScope();
  const snapshot = useCallback(() => searchRestoration.getHref(scope, href), [scope, href]);
  // SSR and the first hydration render both use the original Link destination.
  return useSyncExternalStore(searchRestoration.subscribe, snapshot, () => href);
}

export function useClearSearchRestoration(path: string) {
  const scope = useSearchRestorationScope();
  return useCallback(() => {
    searchRestoration.clear(scope, path);
  }, [scope, path]);
}
