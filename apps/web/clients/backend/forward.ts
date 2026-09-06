import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { ANONYMOUS_CHAT_TTL_SECONDS, backendConfig } from "../../config/backend";
import { logError, logInfo } from "../../lib/observability/logger";
import { REQUEST_ID_HEADER, resolveRequestId } from "../../lib/observability/request-id";
import { attachIdentity, resolveBackendIdentity } from "./identity";

const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "last-event-id"] as const;

function forwardedHeaders(requestHeaders: Headers): Headers {
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = requestHeaders.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

/**
 * Next.js 微后端 → FastAPI 转发。
 * 浏览器只打同源 `/api/v1`；此处补上登录身份并去掉 Cookie，避免把 Better Auth 会话泄漏给 Python。
 */
export async function forwardToBusinessBackend(
  req: NextRequest,
  backendOrigin: string,
  path: string[],
) {
  const route = `/api/v1/${path.join("/")}`;
  const dest = `${backendOrigin.replace(/\/$/, "")}${route}${req.nextUrl.search}`;
  const requestId = resolveRequestId(req.headers.get(REQUEST_ID_HEADER));
  const startedAt = performance.now();
  // Browser headers are untrusted. Only copy headers the business protocol needs.
  const headers = forwardedHeaders(req.headers);
  headers.set(REQUEST_ID_HEADER, requestId);
  const cookie = req.cookies.get("shenzhi-chat-anon")?.value;
  const anonymousId = cookie && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(cookie)
    ? cookie : randomUUID();
  if (backendConfig.secret) headers.set("x-shenzhi-bff-secret", backendConfig.secret);

  let identity: Awaited<ReturnType<typeof resolveBackendIdentity>>;
  try {
    identity = await resolveBackendIdentity(req.headers);
    attachIdentity(headers, identity, anonymousId);
  } catch {
    const response = NextResponse.json(
      { code: 10001, message: "鉴权服务异常，请稍后重试" },
      { status: 503 },
    );
    response.headers.set(REQUEST_ID_HEADER, requestId);
    return response;
  }

  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
    signal: req.signal,
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    Object.assign(init, { body: req.body, duplex: "half" });
  }

  let upstream: Response;
  try { upstream = await fetch(dest, init); }
  catch (error) {
    logError("bff.backend.failed", {
      request_id: requestId,
      method: req.method,
      route,
      duration_ms: Math.round(performance.now() - startedAt),
      error_type: error instanceof Error ? error.name : "UnknownError",
    });
    const response = NextResponse.json({ code: 20004, message: "无法连接生成服务，请稍后重试" }, { status: 503 });
    response.headers.set(REQUEST_ID_HEADER, requestId);
    return response;
  }
  const out = new Headers(upstream.headers);
  out.delete("content-encoding");
  out.delete("transfer-encoding");
  out.delete("set-cookie");
  out.set("Cache-Control", "no-store, no-transform");
  out.set(REQUEST_ID_HEADER, requestId);

  logInfo("bff.backend.completed", {
    request_id: requestId,
    method: req.method,
    route,
    status_code: upstream.status,
    duration_ms: Math.round(performance.now() - startedAt),
  });

  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: out,
  });
  // Only anonymous traffic renews this access key. An authenticated request
  // must not silently extend data that has already been (or will be) claimed.
  if (identity.kind === "anonymous" && upstream.ok) response.cookies.set("shenzhi-chat-anon", anonymousId, {
    httpOnly: true, sameSite: "lax", secure: req.nextUrl.protocol === "https:", path: "/", maxAge: ANONYMOUS_CHAT_TTL_SECONDS,
  });
  return response;
}
