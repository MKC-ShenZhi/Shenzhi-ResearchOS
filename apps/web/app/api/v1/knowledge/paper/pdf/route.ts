import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

import { attachIdentity, resolveBackendIdentity } from "@/clients/backend/identity";
import { backendConfig, backendConnectionIsAllowed } from "@/config/backend";
import { logError, logInfo } from "@/lib/observability/logger";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/observability/request-id";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PDF_REQUEST_HEADERS = ["accept", "range"] as const;
const PDF_RESPONSE_HEADERS = [
  "content-length",
  "content-disposition",
  "accept-ranges",
  "content-range",
  "cache-control",
] as const;

function withRequestId(response: NextResponse, requestId: string) {
  response.headers.set(REQUEST_ID_HEADER, requestId);
  return response;
}

function errorResponse(requestId: string, message: string, status = 503) {
  return withRequestId(NextResponse.json({ code: 20004, message }, { status }), requestId);
}

function forwardedHeaders(request: NextRequest, requestId: string): Headers {
  const headers = new Headers();
  for (const name of PDF_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set(REQUEST_ID_HEADER, requestId);
  if (backendConfig.secret) headers.set("X-ShenZhi-Bff-Secret", backendConfig.secret);
  return headers;
}

function responseHeaders(upstream: Response, requestId: string): Headers {
  const headers = new Headers();
  headers.set(
    "Content-Type",
    upstream.ok
      ? upstream.headers.get("content-type") ?? "application/pdf"
      : "application/json",
  );
  for (const name of PDF_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set(REQUEST_ID_HEADER, requestId);
  return headers;
}

export async function GET(request: NextRequest) {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const startedAt = performance.now();

  if (!backendConfig.url) {
    return errorResponse(requestId, "生成服务未配置", 503);
  }
  if (!backendConnectionIsAllowed(backendConfig)) {
    return errorResponse(requestId, "后端调用凭据未配置", 503);
  }

  const headers = forwardedHeaders(request, requestId);
  try {
    const identity = await resolveBackendIdentity(request.headers);
    attachIdentity(headers, identity, randomUUID());
  } catch {
    return errorResponse(requestId, "鉴权服务异常，请稍后重试", 503);
  }

  const destination = `${backendConfig.url.replace(/\/$/, "")}/api/v1/knowledge/paper/pdf${request.nextUrl.search}`;
  let upstream: Response;
  try {
    upstream = await fetch(destination, {
      method: "GET",
      headers,
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    });
  } catch (error) {
    logError("bff.pdf.failed", {
      request_id: requestId,
      route: "/api/v1/knowledge/paper/pdf",
      method: "GET",
      duration_ms: Math.round(performance.now() - startedAt),
      error_type: error instanceof Error ? error.name : "UnknownError",
    });
    return errorResponse(requestId, "无法连接 PDF 服务，请稍后重试", 503);
  }

  logInfo("bff.pdf.completed", {
    request_id: requestId,
    route: "/api/v1/knowledge/paper/pdf",
    method: "GET",
    status_code: upstream.status,
    duration_ms: Math.round(performance.now() - startedAt),
  });

  return withRequestId(new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders(upstream, requestId),
  }), requestId);
}
