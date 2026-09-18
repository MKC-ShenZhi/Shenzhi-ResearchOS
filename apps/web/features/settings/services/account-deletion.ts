// This browser-facing service only reads the standard response header; keeping
// the literal local also lets the isolated Node test runtime load this module.
const REQUEST_ID_HEADER = "X-Request-Id";

export type AccountDeletionResult =
  | { ok: true }
  | { ok: false; message: string; status?: number; requestId?: string };

/** Calls the server-side deletion orchestrator; the browser never selects a user id. */
export async function deleteCurrentAccount(): Promise<AccountDeletionResult> {
  let response: Response;
  try {
    response = await fetch("/api/auth/account-deletion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch {
    return { ok: false, message: "账号注销服务暂不可用，请稍后重试" };
  }
  if (response.ok) return { ok: true };
  const payload = await response.json().catch(() => null) as { message?: string } | null;
  const requestId = response.headers.get(REQUEST_ID_HEADER) ?? undefined;
  return {
    ok: false,
    message: payload?.message ?? "账号注销失败，请稍后重试",
    status: response.status,
    requestId,
  };
}
