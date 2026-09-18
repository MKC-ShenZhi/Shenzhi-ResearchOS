export type AccountDeletionResult =
  | { ok: true }
  | { ok: false; message: string; status?: number };

/** Calls the server-side deletion orchestrator; the browser never selects a user id. */
export async function deleteCurrentAccount(): Promise<AccountDeletionResult> {
  const response = await fetch("/api/auth/account-deletion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (response.ok) return { ok: true };
  const payload = await response.json().catch(() => null) as { message?: string } | null;
  return { ok: false, message: payload?.message ?? "账号注销失败，请稍后重试", status: response.status };
}
