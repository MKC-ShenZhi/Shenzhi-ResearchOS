import { buildKnowledgeSearchUrl, readKnowledgeSearchUrlState } from "./search-url-state";

const PREFIX = "shenzhi:paper-search-scroll:";
const MAX_AGE_MS = 30 * 60_000;

type ScrollStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function storageKey(returnTo: string): string {
  const url = new URL(returnTo, "https://shenzhi-internal.invalid");
  return PREFIX + buildKnowledgeSearchUrl(readKnowledgeSearchUrlState(url.searchParams));
}

export function saveSearchScroll(storage: ScrollStorage, returnTo: string, top: number, now = Date.now()): void {
  if (!Number.isFinite(top) || top < 0) return;
  try {
    storage.setItem(storageKey(returnTo), JSON.stringify({ top, savedAt: now }));
  } catch {
    // Disabled/full session storage must never prevent opening a paper.
  }
}

export function clearSearchScroll(storage: ScrollStorage, returnTo: string): void {
  try {
    storage.removeItem(storageKey(returnTo));
  } catch {
    // Browsing still works when storage is unavailable.
  }
}

export function readSearchScroll(storage: ScrollStorage, returnTo: string, now = Date.now()): number | null {
  try {
    const raw = storage.getItem(storageKey(returnTo));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value === "object" && value !== null && "top" in value && "savedAt" in value &&
        typeof value.top === "number" && Number.isFinite(value.top) && value.top >= 0 &&
        typeof value.savedAt === "number" && value.savedAt <= now && now - value.savedAt <= MAX_AGE_MS) {
      return value.top;
    }
    clearSearchScroll(storage, returnTo);
  } catch {
    clearSearchScroll(storage, returnTo);
  }
  return null;
}
