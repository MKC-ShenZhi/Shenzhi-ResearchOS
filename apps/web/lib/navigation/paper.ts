import { appendInternalReturnTo, normalizeInternalReturnTo } from "./internal-return-to";

type PaperHrefOptions = {
  graph?: boolean;
} & (
  | { mode: "create"; source: string | null | undefined; returnTo?: never }
  | { mode: "preserve"; returnTo: string | null | undefined; source?: never }
  | { mode?: never; source?: never; returnTo?: never }
);

const PAPER_SCOPE_PATH = /^\/papers\/[^/]+(?:\/graph)?\/?$/;
const LEGACY_PAPER_SCOPE_PATH = /^\/knowledge\/search\/[^/]+(?:\/graph)?\/?$/;

/** Keep returnTo anchored outside Paper scope, even when given an already-nested legacy URL. */
function paperReturnTo(options?: PaperHrefOptions): string | null {
  let candidate = normalizeInternalReturnTo(
    options?.mode === "create"
      ? options.source
      : options?.mode === "preserve"
        ? options.returnTo
        : null,
  );
  const visited = new Set<string>();

  while (typeof candidate === "string" && !visited.has(candidate)) {
    visited.add(candidate);

    try {
      const parsed = new URL(candidate, "https://shenzhi-internal.invalid");
      if (!PAPER_SCOPE_PATH.test(parsed.pathname) && !LEGACY_PAPER_SCOPE_PATH.test(parsed.pathname)) {
        return candidate;
      }
      candidate = normalizeInternalReturnTo(parsed.searchParams.get("returnTo"));
    } catch {
      return null;
    }
  }

  return null;
}

/** Restore one URL path segment to the raw opaque ID used inside the application. */
export function paperIdFromRouteParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/** IDs are raw and opaque inside the app; encode them only when building a URL. */
export function paperHref(id: string, options?: PaperHrefOptions): string {
  return appendInternalReturnTo(
    `/papers/${encodeURIComponent(id)}${options?.graph ? "/graph" : ""}`,
    paperReturnTo(options),
  );
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
