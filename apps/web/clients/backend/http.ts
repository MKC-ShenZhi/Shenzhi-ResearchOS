import type { ApiEnvelope } from "../../types/ai-search";

/** 浏览器一律打同源 `/api/v1`，由 Next 微后端转发到 FastAPI（BUSINESS_BACKEND_URL） */
export const API_PREFIX = "/api/v1";

export interface ApiErrorOptions {
  retryable?: boolean;
  requestId?: string | null;
}

export class ApiError extends Error {
  code: number | string;
  status: number;
  retryable: boolean | undefined;
  requestId: string | null;

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
  }
}

export function apiPath(path: string) {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_PREFIX}${p}`;
}

/** Backend identity is supplied only by the same-origin BFF. */
export function requestHeaders(extra?: HeadersInit): Headers {
  return new Headers(extra);
}

// Serialize first contact so parallel config/history/upload requests cannot issue
// different anonymous cookies. This is transport bootstrap, not an account system.
let identityReady: Promise<void> | undefined;
async function ensureBackendIdentity() {
  if (typeof window === "undefined") return;
  identityReady ??= fetch(apiPath("/chat/config"), { cache: "no-store", signal: AbortSignal.timeout(30000) }).then((response) => {
    if (!response.ok) throw new ApiError(20004, "无法连接生成服务", response.status);
  }).catch((error) => { identityReady = undefined; throw error; });
  await identityReady;
}

export async function apiJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  await ensureBackendIdentity();
  const headers = requestHeaders(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(apiPath(path), { ...init, headers, signal: init.signal ?? AbortSignal.timeout(30000) });
  if (res.status === 204) return undefined as T;
  let payload: unknown;
  try {
    payload = await res.json();
  } catch {
    throw new ApiError(
      20004,
      res.ok ? "响应无法解析" : `请求失败 (${res.status})`,
      res.status,
    );
  }

  if (isKnowledgeErrorPayload(payload)) {
    throw new ApiError(payload.code, payload.message, res.status, {
      retryable: payload.retryable,
      requestId: payload.requestId,
    });
  }

  const envelope = isRecord(payload) ? (payload as Partial<ApiEnvelope<T>>) : null;
  if (!res.ok || !envelope || envelope.code !== 0 || envelope.data === undefined) {
    throw new ApiError(
      envelope?.code ?? 20004,
      envelope?.message || "生成服务暂不可用",
      res.status,
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
