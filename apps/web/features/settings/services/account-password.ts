/** OAuth 用户通过邮箱 OTP 设置初始密码（Better Auth `/api/auth/password/*`）。 */

export type AccountPasswordResult =
  | { ok: true }
  | { ok: false; message: string };

async function readJsonMessage(response: Response): Promise<string | undefined> {
  const data = (await response.json().catch(() => null)) as { message?: string } | null;
  return data?.message;
}

export async function sendSetPasswordOtp(): Promise<AccountPasswordResult> {
  let response: Response;
  try {
    response = await fetch("/api/auth/password/send-otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch {
    return { ok: false, message: "send_otp_failed" };
  }
  if (!response.ok) {
    return { ok: false, message: (await readJsonMessage(response)) ?? "send_otp_failed" };
  }
  return { ok: true };
}

export async function setPasswordWithOtp(
  otp: string,
  newPassword: string,
): Promise<AccountPasswordResult> {
  let response: Response;
  try {
    response = await fetch("/api/auth/password/set", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ otp, newPassword }),
    });
  } catch {
    return { ok: false, message: "set_password_failed" };
  }
  if (!response.ok) {
    return { ok: false, message: (await readJsonMessage(response)) ?? "set_password_failed" };
  }
  return { ok: true };
}
