type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export type SearchDraftEntry = "home-search" | "/knowledge/search";
const ENTRIES: SearchDraftEntry[] = ["home-search", "/knowledge/search"];
const PREFIX = "shenzhi:search-draft:v1:";
const MAX_AGE = 30 * 60 * 1000;
const MAX_LENGTH = 2000;
type Draft = { source: string; value: string; updatedAt: number };

/** Only short text drafts. URL state, results and attachments remain with their owners. */
export function createSearchDrafts(getStorage: () => DraftStorage | null, now = Date.now) {
  const listeners = new Set<() => void>();
  // Also provides normal editing when browser storage is disabled.
  const memory = new Map<string, Draft | null>();
  let activeScope: string | null = null;
  const key = (scope: string, entry: SearchDraftEntry) => `${PREFIX}${encodeURIComponent(scope)}:${entry}`;
  const notify = () => listeners.forEach((listener) => listener());
  function read(recordKey: string): Draft | null {
    if (memory.has(recordKey)) return memory.get(recordKey) ?? null;
    try {
      const raw = getStorage()?.getItem(recordKey);
      if (!raw) return null;
      const record = JSON.parse(raw) as Partial<Draft>;
      if (typeof record.source !== "string" || typeof record.value !== "string" || record.value.length > MAX_LENGTH ||
        typeof record.updatedAt !== "number" || !Number.isFinite(record.updatedAt)) return null;
      return record as Draft;
    } catch { return null; }
  }
  function remove(recordKey: string) {
    memory.set(recordKey, null);
    try { getStorage()?.removeItem(recordKey); } catch { /* The in-memory tombstone prevents revival. */ }
  }
  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    activate(scope: string) {
      if (activeScope && activeScope !== scope) {
        for (const entry of ENTRIES) remove(key(activeScope, entry));
        notify();
      }
      activeScope = scope;
    },
    get(scope: string | null, entry: SearchDraftEntry, source: string, fallback: string) {
      if (!scope) return fallback;
      const record = read(key(scope, entry));
      if (!record || record.source !== source || now() - record.updatedAt > MAX_AGE || record.updatedAt > now()) return fallback;
      return record.value;
    },
    set(scope: string | null, entry: SearchDraftEntry, source: string, value: string) {
      if (!scope) return;
      const recordKey = key(scope, entry);
      const record: Draft = { source, value: value.slice(0, MAX_LENGTH), updatedAt: now() };
      memory.set(recordKey, record);
      try { getStorage()?.setItem(recordKey, JSON.stringify(record)); } catch { /* Editing still works. */ }
      notify();
    },
    clear(scope: string | null, entry: SearchDraftEntry) {
      if (!scope) return;
      remove(key(scope, entry));
      notify();
    },
  };
}

export const searchDrafts = createSearchDrafts(() => typeof window === "undefined" ? null : window.sessionStorage);
