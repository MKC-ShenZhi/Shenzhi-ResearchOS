import { appendInternalReturnTo } from "./internal-return-to";

/** Restore one URL path segment to the raw opaque ID used inside the application. */
export function paperIdFromRouteParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/** IDs are raw and opaque inside the app; encode them only when building a URL. */
export function paperHref(id: string, returnTo?: string | null, graph = false): string {
  return appendInternalReturnTo(`/papers/${encodeURIComponent(id)}${graph ? "/graph" : ""}`, returnTo);
}

export function paperExternalUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export function paperDoiUrl(doi: string | null): string | null {
  if (!doi?.trim()) return null;
  const value = doi.trim();
  return /^https?:\/\//i.test(value)
    ? paperExternalUrl(value)
    : `https://doi.org/${value.replace(/^doi:\s*/i, "")}`;
}
