import { NextRequest, NextResponse } from "next/server";

import { backendConfig, backendConnectionIsAllowed } from "@/config/backend";
import { auth } from "@/lib/auth/server";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/observability/request-id";

const CLEANUP_PATH = "/api/v1/account-deletion/cleanup";

function response(message: string, status: number, requestId: string) {
  const result = NextResponse.json({ message }, { status });
  result.headers.set(REQUEST_ID_HEADER, requestId);
  return result;
}

/**
 * Orchestrates irreversible account deletion without exposing the business
 * cleanup endpoint to the browser. The FastAPI cleanup is idempotent, so a
 * Better Auth failure after cleanup can be retried safely after re-login.
 */
export async function POST(request: NextRequest) {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session?.user.id) return response("请先登录后注销账号", 401, requestId);
  if (!backendConfig.url || !backendConnectionIsAllowed(backendConfig)) {
    return response("业务数据清理服务暂不可用，账号尚未删除", 503, requestId);
  }

  const cleanupHeaders = new Headers({
    "X-ShenZhi-User-Id": session.user.id,
    "X-ShenZhi-Account-Deletion": "1",
    [REQUEST_ID_HEADER]: requestId,
  });
  if (backendConfig.secret) {
    cleanupHeaders.set("X-ShenZhi-Bff-Secret", backendConfig.secret);
  }

  let cleanup: Response;
  try {
    cleanup = await fetch(
      `${backendConfig.url.replace(/\/$/, "")}${CLEANUP_PATH}`,
      { method: "POST", headers: cleanupHeaders, cache: "no-store", signal: request.signal },
    );
  } catch {
    return response("业务数据清理服务暂不可用，账号尚未删除", 503, requestId);
  }
  if (!cleanup.ok) {
    return response("个人数据清理失败，账号尚未删除，请稍后重试", 503, requestId);
  }

  // Let Better Auth enforce its sensitive-session/fresh-session policy. It
  // owns the user, account, session, and verification tables exclusively.
  const deletion = await auth.api.deleteUser({
    headers: request.headers,
    body: {},
  });
  if (!deletion || ("error" in deletion && deletion.error)) {
    return response("个人数据已清理；请重新登录后重试最终账号注销", 409, requestId);
  }

  const result = NextResponse.json({ success: true }, { status: 200 });
  result.headers.set(REQUEST_ID_HEADER, requestId);
  return result;
}
