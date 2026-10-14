import { normalizeInternalReturnTo } from "./internal-return-to";

/** Navigation parameters only. Features remain responsible for business validation. */
export const SEARCH_RESTORATION_ROUTES: Readonly<Record<string, readonly string[]>> = {
  "/knowledge/search": ["q", "page", "yearFrom", "yearTo", "venue", "author", "keyword", "subject"],
  "/knowledge/scholars": ["q"],
  "/knowledge/topics": ["q", "category"],
  "/knowledge/funding": ["q", "funding"],
};

export function normalizeSearchRestorationHref(value: unknown): string | null {
  const safe = normalizeInternalReturnTo(value);
  if (!safe || safe.includes("#")) return null;
  const path = safe.split("?", 1)[0];
  // Literal exact matching rejects detail routes, encoded paths and dot segments.
  if (!Object.hasOwn(SEARCH_RESTORATION_ROUTES, path)) return null;
  const allowed = SEARCH_RESTORATION_ROUTES[path];
  const params = new URLSearchParams();
  for (const [key, value] of new URL(safe, "https://shenzhi-internal.invalid").searchParams) {
    if (allowed.includes(key) && value.trim()) params.append(key, value);
  }
  return params.size ? `${path}?${params.toString()}` : null;
}

type NavigationStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const STORAGE_PREFIX = "shenzhi:search-navigation:v1:";

/** Storage boundary is injectable; no API responses or duplicate search state are kept. */
export function createSearchRestoration(getStorage: () => NavigationStorage | null) {
  const listeners = new Set<() => void>();
  const pendingClears = new Set<string>();
  let unavailable = false;
  let activeScope: string | null = null;
  let blockedHref: string | null = null;
  const notify = () => listeners.forEach((listener) => listener());
  const key = (scope: string, path: string) => `${STORAGE_PREFIX}${encodeURIComponent(scope)}:${path}`;

  function access<T>(operation: (storage: NavigationStorage) => T): T | null {
    if (unavailable) return null;
    try {
      const storage = getStorage();
      return storage ? operation(storage) : null;
    } catch {
      // A failed clear/write must not revive an old record later in this runtime.
      unavailable = true;
      return null;
    }
  }

  function clearRecord(scope: string, path: string) {
    access((storage) => storage.removeItem(key(scope, path)));
    notify();
  }

  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    getHref(scope: string | null, href: string): string {
      // Only bare registered navigation entries restore. Explicit URLs always win.
      if (!scope || !Object.hasOwn(SEARCH_RESTORATION_ROUTES, href)) return href;
      const saved = normalizeSearchRestorationHref(access((storage) => storage.getItem(key(scope, href))));
      return saved?.split("?", 1)[0] === href ? saved : href;
    },
    record(scope: string, href: string) {
      // Clearing before the first auth response must not leave an old record behind.
      for (const path of pendingClears) clearRecord(scope, path);
      pendingClears.clear();
      // Auth changes do not turn the URL left by the previous user into a new record.
      // Kept across AppShell remounts; recording resumes when the URL changes.
      if (activeScope !== null && activeScope !== scope) blockedHref = href;
      activeScope = scope;
      if (blockedHref === href) return;
      blockedHref = null;
      const saved = normalizeSearchRestorationHref(href);
      if (!saved) return; // Visiting a bare route is different from explicitly clearing it.
      const path = saved.split("?", 1)[0];
      access((storage) => storage.setItem(key(scope, path), saved));
      notify();
    },
    clear(scope: string | null, path: string) {
      if (!Object.hasOwn(SEARCH_RESTORATION_ROUTES, path)) return;
      if (scope) clearRecord(scope, path);
      else pendingClears.add(path);
    },
  };
}

export const searchRestoration = createSearchRestoration(() =>
  typeof window === "undefined" ? null : window.sessionStorage,
);
