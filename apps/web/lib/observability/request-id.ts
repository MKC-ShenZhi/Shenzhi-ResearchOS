import { randomUUID } from "node:crypto";

export const REQUEST_ID_HEADER = "X-Request-ID";

const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export function normalizeRequestId(
  value: string | null | undefined,
): string | undefined {
  if (typeof value !== "string") return undefined;
  const normalized = value.trim();
  return REQUEST_ID_PATTERN.test(normalized) ? normalized : undefined;
}

export function createRequestId(): string {
  return randomUUID();
}

export function resolveRequestId(value: string | null | undefined): string {
  return normalizeRequestId(value) ?? createRequestId();
}
