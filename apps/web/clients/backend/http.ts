import { BACKEND_IDENTITY_EVENT, BACKEND_IDENTITY_HEADER } from "./identity-response";
import type { ApiEnvelope } from "./types";

/** 浏览器一律打同源 `/api/v1`，由 Next 微后端转发到 FastAPI（BUSINESS_BACKEND_URL） */
export const API_PREFIX = "/api/v1";

export interface ApiErrorOptions {
  retryable?: boolean;
  requestId?: string | null;
  sessionMismatch?: boolean;
}

export class ApiError extends Error {
  code: number | string;
  status: number;
  retryable: boolean | undefined;
  requestId: string | null;
  sessionMismatch: boolean;

  constructor(
    code: number | string,
    message: string,
    status = 400,
    options: ApiErrorOptions = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryable = options.retryable;
    this.requestId = options.requestId ?? null;
    this.sessionMismatch = options.sessionMismatch ?? false;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export function isSessionMismatchError(error: unknown): boolean {
  return error instanceof ApiError && error.sessionMismatch;
}

export function requestIdForApiError(error: unknown): string | undefined {
  return error instanceof ApiError ? error.requestId ?? undefined : undefined;
}

export function apiPath(path: string) {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_PREFIX}${p}`;
}

/** Backend identity is supplied only by the same-origin BFF. */
export function requestHeaders(extra?: HeadersInit): Headers {
  return new Headers(extra);
}

/** Reject a request if cookies changed accounts before the BFF resolved them.
 * This is a precondition, never an authentication credential.
 */
export function expectedUserHeaders(userId: string): HeadersInit {
  return { "x-shenzhi-expected-user-id": userId };
}

export async function fetchBackend(url: string, init: RequestInit) {
  const response = await fetch(url, init);
  const kind = response.headers.get(BACKEND_IDENTITY_HEADER);
  let sessionMismatch = false;
  if (
    typeof window !== "undefined" &&
    url.startsWith(`${API_PREFIX}/`) &&
    !response.redirected &&
    (kind === "authenticated" || kind === "anonymous")
  ) {
    // The provider claims anonymous 401s that it is handling as a session mismatch.
    sessionMismatch = !window.dispatchEvent(new CustomEvent(BACKEND_IDENTITY_EVENT, {
      detail: kind,
      cancelable: kind === "anonymous" && response.status === 401,
    }));
  }
  return { response, sessionMismatch };
}

// Serialize first contact so parallel config/history/upload requests cannot issue
// different anonymous cookies. This is transport bootstrap, not an account system.
let identityReady: Promise<void> | undefined;
async function ensureBackendIdentity() {
  if (typeof window === "undefined") return;
  identityReady ??= fetchBackend(apiPath("/identity/bootstrap"), {
    cache: "no-store",
    signal: AbortSignal.timeout(30000),
  }).then(({ response, sessionMismatch }) => {
    if (!response.ok) throw new ApiError(20004, "无法连接生成服务", response.status, {
      requestId: response.headers.get("X-Request-ID"),
      sessionMismatch,
    });
  }).catch((error) => { identityReady = undefined; throw error; });
  await identityReady;
}

export async function apiJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  init.signal?.throwIfAborted();
  await ensureBackendIdentity();
  init.signal?.throwIfAborted();
  const headers = requestHeaders(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const timeout = AbortSignal.timeout(30000);
  const { response: res, sessionMismatch } = await fetchBackend(apiPath(path), {
    ...init,
    headers,
    signal: init.signal ? AbortSignal.any([init.signal, timeout]) : timeout,
  });
  const requestId = res.headers.get("X-Request-ID");
  if (res.status === 204) return undefined as T;
  let payload: unknown;
  try {
    payload = await res.json();
  } catch {
    throw new ApiError(
      20004,
      res.ok ? "响应无法解析" : `请求失败 (${res.status})`,
      res.status,
      { requestId, sessionMismatch },
    );
  }

  if (isKnowledgeErrorPayload(payload)) {
    throw new ApiError(payload.code, payload.message, res.status, {
      retryable: payload.retryable,
      requestId: payload.requestId ?? requestId,
      sessionMismatch,
    });
  }

  const envelope = isRecord(payload) ? (payload as Partial<ApiEnvelope<T>>) : null;
  if (!res.ok || !envelope || envelope.code !== 0 || envelope.data === undefined) {
    throw new ApiError(
      envelope?.code ?? 20004,
      envelope?.message || "生成服务暂不可用",
      res.status,
      { requestId, sessionMismatch },
    );
  }

  return envelope.data;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isKnowledgeErrorPayload(
  value: unknown,
): value is {
  code: string;
  message: string;
  retryable: boolean;
  requestId: string | null;
} {
  if (!isRecord(value)) return false;
  return typeof value.code === "string" &&
    typeof value.message === "string" &&
    typeof value.retryable === "boolean" &&
    (value.requestId === null || typeof value.requestId === "string");
}
