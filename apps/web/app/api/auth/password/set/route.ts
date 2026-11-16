import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/lib/auth/server";
import {
  hashSetPasswordOtp,
  otpMatches,
  parseSetPasswordOtpValue,
  SET_PASSWORD_OTP_ALLOWED_ATTEMPTS,
  setPasswordOtpIdentifier,
} from "@/lib/auth/password/otp";
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  validatePasswordComposition,
} from "@/lib/auth/policies/password";
import { hasPasswordFromAccounts } from "@/lib/auth/password/status";
import { OAUTH_CREDENTIAL_PROVIDER_ID } from "@/lib/auth/providers/oauth/credential";

function errorResponse(message: string, code: string, status: number) {
  return NextResponse.json({ error: code, message }, { status });
}

/**
 * 为「尚无真实密码」的用户（如 GitHub OAuth 注册）设置密码。
 *
 * 流程：要求已登录 → 用邮箱验证码证明邮箱所有权 → 写入真实密码并
 * 清除 credential 账户上的随机占位符标记。
 */
export async function POST(request: NextRequest) {
  const session = await auth.api.getSession({ headers: request.headers });
  const user = session?.user;
  if (!user?.id || !user.email) {
    return errorResponse("请先登录", "UNAUTHORIZED", 401);
  }

  let otp: string | null = null;
  let newPassword: string | null = null;

  const contentType = request.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const body = (await request.json().catch(() => null)) as {
      otp?: unknown;
      newPassword?: unknown;
    } | null;
    otp = typeof body?.otp === "string" ? body.otp.trim() : null;
    newPassword =
      typeof body?.newPassword === "string" ? body.newPassword : null;
  }

  if (!otp || !/^\d{6}$/.test(otp)) {
    return errorResponse("请输入6位数字验证码", "INVALID_OTP", 400);
  }

  if (
    !newPassword ||
    newPassword.length < PASSWORD_MIN_LENGTH ||
    newPassword.length > PASSWORD_MAX_LENGTH ||
    !validatePasswordComposition(newPassword).valid
  ) {
    return errorResponse(
      "密码需为12–64位，且至少包含大写字母、小写字母和数字",
      "PASSWORD_POLICY_VIOLATION",
      400,
    );
  }

  const ctx = await auth.$context;
  const identifier = setPasswordOtpIdentifier(user.id);
  const accounts = await ctx.internalAdapter.findAccounts(user.id);
  if (hasPasswordFromAccounts(accounts)) {
    return errorResponse(
      "当前账户已有密码，请使用修改密码功能",
      "PASSWORD_ALREADY_SET",
      409,
    );
  }

  // 1. 校验邮箱验证码（会话绑定本人邮箱，单次使用）。
  const existing =
    await ctx.internalAdapter.findVerificationValue(identifier);
  if (existing && existing.expiresAt < new Date()) {
    await ctx.internalAdapter.deleteVerificationByIdentifier(identifier);
    return errorResponse("验证码已过期，请重新获取", "OTP_EXPIRED", 400);
  }

  const consumed =
    await ctx.internalAdapter.consumeVerificationValue(identifier);
  if (!consumed) {
    return errorResponse("验证码错误，请检查后重试", "INVALID_OTP", 400);
  }

  const stored = parseSetPasswordOtpValue(consumed.value);
  if (!stored) {
    return errorResponse("验证码错误，请检查后重试", "INVALID_OTP", 400);
  }

  if (stored.attempts >= SET_PASSWORD_OTP_ALLOWED_ATTEMPTS) {
    return errorResponse(
      "验证码尝试次数过多，请重新获取",
      "TOO_MANY_ATTEMPTS",
      400,
    );
  }

  const candidateHash = await hashSetPasswordOtp(user.id, otp, ctx.secret);
  if (!(await otpMatches(candidateHash, stored.otpHash))) {
    await ctx.internalAdapter.createVerificationValue({
      identifier,
      value: JSON.stringify({ ...stored, attempts: stored.attempts + 1 }),
      expiresAt: consumed.expiresAt,
    });
    return errorResponse("验证码错误，请检查后重试", "INVALID_OTP", 400);
  }

  // 2. 写入真实密码，并清除占位符标记。
  const hash = await ctx.password.hash(newPassword);
  const credential = accounts.find(
    (account) => account.providerId === OAUTH_CREDENTIAL_PROVIDER_ID,
  );

  if (credential) {
    await ctx.internalAdapter.updateAccount(credential.id, {
      password: hash,
      scope: null,
    });
  } else {
    await ctx.internalAdapter.linkAccount({
      userId: user.id,
      providerId: OAUTH_CREDENTIAL_PROVIDER_ID,
      accountId: user.id,
      password: hash,
    });
  }

  return NextResponse.json({ success: true });
}
