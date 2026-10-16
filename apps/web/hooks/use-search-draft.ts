"use client";

import { useCallback, useSyncExternalStore } from "react";
import { searchDrafts, type SearchDraftEntry } from "@/lib/navigation/search-draft";
import { useSearchRestorationScope } from "./use-search-restoration";

export function useSearchDraft(entry: SearchDraftEntry, source: string, fallback = "") {
  const scope = useSearchRestorationScope();
  const snapshot = useCallback(() => searchDrafts.get(scope, entry, source, fallback), [scope, entry, source, fallback]);
  const value = useSyncExternalStore(searchDrafts.subscribe, snapshot, () => fallback);
  const set = useCallback((next: string) => searchDrafts.set(scope, entry, source, next), [scope, entry, source]);
  const clear = useCallback(() => searchDrafts.clear(scope, entry), [scope, entry]);
  return { value, set, clear, ready: scope !== null };
}
