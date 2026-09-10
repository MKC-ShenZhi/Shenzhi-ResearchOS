import { ApiError } from "@/clients/backend/http";

export function isMissingSessionError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 404;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export function messageForApiError(error: unknown) {
  if (error instanceof ApiError) return error.message || "生成服务暂不可用";
  if (error instanceof Error) return error.message;
  return "生成服务暂不可用";
}

export function requestIdForApiError(error: unknown): string | undefined {
  return error instanceof ApiError ? error.requestId ?? undefined : undefined;
}
