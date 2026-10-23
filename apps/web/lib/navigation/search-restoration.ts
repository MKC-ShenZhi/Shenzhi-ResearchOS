import { normalizeInternalReturnTo } from "./internal-return-to";

/** Navigation parameters only. Features remain responsible for business validation. */
export const SEARCH_RESTORATION_ROUTES: Readonly<Record<string, readonly string[]>> = {
  "/knowledge/search": ["mode", "conference", "year", "q", "page", "yearFrom", "yearTo", "venue", "author", "keyword", "subject"],
  "/knowledge/search/conferences": ["q", "year", "sort", "page"],
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
const PAPER_SEARCH_PATH = "/knowledge/search";
const PAPER_MODE_ENTRIES = ["/knowledge/search?mode=keyword", "/knowledge/search?mode=conference"] as const;

/** Mode-only links are navigation entries; full query URLs remain authoritative. */
function restorationPath(href: string): string | null {
  if (Object.hasOwn(SEARCH_RESTORATION_ROUTES, href)) return href;
  return PAPER_MODE_ENTRIES.some((entry) => entry === href) ? PAPER_SEARCH_PATH : null;
}

function paperModeEntry(href: string): string | null {
  const url = new URL(href, "https://shenzhi-internal.invalid");
  if (url.pathname !== PAPER_SEARCH_PATH) return null;
  const mode = url.searchParams.get("mode");
  const keyword = mode === "keyword" || (mode !== "conference" && Boolean(url.searchParams.get("q")?.trim()));
  return PAPER_MODE_ENTRIES[keyword ? 0 : 1];
}

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
  }

  function clearEntry(scope: string, entry: string) {
    clearRecord(scope, entry);
    if (entry === PAPER_SEARCH_PATH) {
      for (const modeEntry of PAPER_MODE_ENTRIES) clearRecord(scope, modeEntry);
    } else if (restorationPath(entry) === PAPER_SEARCH_PATH) {
      const last = normalizeSearchRestorationHref(access((storage) => storage.getItem(key(scope, PAPER_SEARCH_PATH))));
      if (last && paperModeEntry(last) === entry) clearRecord(scope, PAPER_SEARCH_PATH);
    }
    notify();
  }

  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    getHref(scope: string | null, href: string): string {
      // Restoring a mode entry must never replace it with the other mode's URL.
      const path = restorationPath(href);
      if (!scope || !path) return href;
      const saved = normalizeSearchRestorationHref(access((storage) => storage.getItem(key(scope, href))));
      if (saved?.split("?", 1)[0] === path && (href === path || paperModeEntry(saved) === href)) return saved;
      if (href !== path) {
        // Existing v1 records only stored the last library URL, without mode slots.
        const legacy = normalizeSearchRestorationHref(access((storage) => storage.getItem(key(scope, path))));
        if (legacy && paperModeEntry(legacy) === href) return legacy;
      }
      return href;
    },
    record(scope: string, href: string) {
      // Clearing before the first auth response must not leave an old record behind.
      for (const path of pendingClears) clearEntry(scope, path);
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
      if (path === PAPER_SEARCH_PATH) {
        // Preserve an existing v1 query before a first visit to the other mode
        // replaces the shared last-library URL.
        const previous = normalizeSearchRestorationHref(access((storage) => storage.getItem(key(scope, path))));
        const previousEntry = previous && paperModeEntry(previous);
        if (previous && previousEntry && access((storage) => storage.getItem(key(scope, previousEntry))) === null) {
          access((storage) => storage.setItem(key(scope, previousEntry), previous));
        }
      }
      access((storage) => storage.setItem(key(scope, path), saved));
      const modeEntry = paperModeEntry(saved);
      if (modeEntry) access((storage) => storage.setItem(key(scope, modeEntry), saved));
      notify();
    },
    clear(scope: string | null, path: string) {
      if (!restorationPath(path)) return;
      if (scope) clearEntry(scope, path);
      else pendingClears.add(path);
    },
  };
}

export const searchRestoration = createSearchRestoration(() =>
  typeof window === "undefined" ? null : window.sessionStorage,
);
