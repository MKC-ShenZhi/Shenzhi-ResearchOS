/** Restore one URL path segment to the raw opaque scholar ID used in the app. */
export function scholarIdFromRouteParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/** Scholar IDs stay opaque inside the app and are encoded only at the route boundary. */
export function scholarHref(id: string): string {
  return `/knowledge/scholars/${encodeURIComponent(id)}`;
}
