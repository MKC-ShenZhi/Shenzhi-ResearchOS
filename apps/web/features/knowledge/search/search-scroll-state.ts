import { buildKnowledgeSearchUrl, readKnowledgeSearchUrlState } from "./search-url-state";
import { buildPaperBrowseUrl, readPaperBrowseState } from "./conferences/conference-state";

const PREFIX = "shenzhi:paper-search-scroll:";
const MAX_AGE_MS = 30 * 60_000;

type ScrollStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function storageKey(returnTo: string, scope: string): string {
  const url = new URL(returnTo, "https://shenzhi-internal.invalid");
  const browse = readPaperBrowseState(url.searchParams);
  const href = browse.mode === "conference"
    ? buildPaperBrowseUrl(browse.conference, browse.year, browse.page)
    : buildKnowledgeSearchUrl(readKnowledgeSearchUrlState(url.searchParams));
  return PREFIX + encodeURIComponent(scope) + ":" + href;
}

export function saveSearchScroll(storage: ScrollStorage, returnTo: string, top: number, now = Date.now(), scope = "anonymous"): void {
  if (!Number.isFinite(top) || top < 0) return;
  try {
    storage.setItem(storageKey(returnTo, scope), JSON.stringify({ top, savedAt: now }));
  } catch {
    // Disabled/full session storage must never prevent opening a paper.
  }
}

export function clearSearchScroll(storage: ScrollStorage, returnTo: string, scope = "anonymous"): void {
  try {
    storage.removeItem(storageKey(returnTo, scope));
  } catch {
    // Browsing still works when storage is unavailable.
  }
}

export function readSearchScroll(storage: ScrollStorage, returnTo: string, now = Date.now(), scope = "anonymous"): number | null {
  try {
    const raw = storage.getItem(storageKey(returnTo, scope));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value === "object" && value !== null && "top" in value && "savedAt" in value &&
        typeof value.top === "number" && Number.isFinite(value.top) && value.top >= 0 &&
        typeof value.savedAt === "number" && value.savedAt <= now && now - value.savedAt <= MAX_AGE_MS) {
      return value.top;
    }
    clearSearchScroll(storage, returnTo, scope);
  } catch {
    clearSearchScroll(storage, returnTo, scope);
  }
  return null;
}
