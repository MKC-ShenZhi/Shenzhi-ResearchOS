import { NextRequest, NextResponse } from "next/server";

import { emailDeliveryConfigured } from "@/config/email";
import { auth } from "@/lib/auth/server";
import { createBetterAuthEmailCallbacks } from "@/lib/auth/email/callbacks";
import {
  canResendSetPasswordOtp,
  createSetPasswordOtpValue,
  generateSetPasswordOtp,
  hashSetPasswordOtp,
  parseSetPasswordOtpValue,
  SET_PASSWORD_OTP_RESEND_COOLDOWN_SECONDS,
  SET_PASSWORD_OTP_EXPIRES_IN_SECONDS,
  setPasswordOtpIdentifier,
} from "@/lib/auth/password/otp";
import { hasPasswordFromAccounts } from "@/lib/auth/password/status";
import { createAuthEmailProvider } from "@/lib/auth/providers/email";

/**
 * 向当前登录用户自己的邮箱发送「设置密码」验证码。
 *
 * 该端点要求已登录（会话绑定本人邮箱），因此无需人机验证；
 * 验证码只发给当前会话所属账号的邮箱。
 */
export async function POST(request: NextRequest) {
  const session = await auth.api.getSession({ headers: request.headers });
  const user = session?.user;
  if (!user?.id || !user.email) {
    return NextResponse.json(
      { error: "UNAUTHORIZED", message: "请先登录" },
      { status: 401 },
    );
  }

  if (!emailDeliveryConfigured) {
    return NextResponse.json(
      {
        error: "EMAIL_PROVIDER_NOT_CONFIGURED",
        message: "邮件服务尚未配置，暂时无法发送邮件",
      },
      { status: 503 },
    );
  }

  const ctx = await auth.$context;
  const identifier = setPasswordOtpIdentifier(user.id);
  const accounts = await ctx.internalAdapter.findAccounts(user.id);
  if (hasPasswordFromAccounts(accounts)) {
    return NextResponse.json(
      {
        error: "PASSWORD_ALREADY_SET",
        message: "当前账户已有密码，请使用修改密码功能",
      },
      { status: 409 },
    );
  }

  const existing = await ctx.internalAdapter.findVerificationValue(identifier);
  const existingValue = existing
    ? parseSetPasswordOtpValue(existing.value)
    : null;
  if (
    existing &&
    existing.expiresAt >= new Date() &&
    existingValue &&
    !canResendSetPasswordOtp(existingValue)
  ) {
    return NextResponse.json(
      {
        error: "OTP_RESEND_COOLDOWN",
        message: `请在 ${SET_PASSWORD_OTP_RESEND_COOLDOWN_SECONDS} 秒后再试`,
      },
      { status: 429 },
    );
  }

  const otp = generateSetPasswordOtp();
  const otpHash = await hashSetPasswordOtp(user.id, otp, ctx.secret);

  await ctx.internalAdapter.createVerificationValue({
    identifier,
    value: JSON.stringify(createSetPasswordOtpValue(otpHash)),
    expiresAt: new Date(
      Date.now() + SET_PASSWORD_OTP_EXPIRES_IN_SECONDS * 1000,
    ),
  });

  const emailCallbacks = createBetterAuthEmailCallbacks(
    createAuthEmailProvider(),
  );
  try {
    await emailCallbacks.sendVerificationOTP({
      email: user.email,
      otp,
      type: "set-password",
    });
  } catch (error) {
    await ctx.internalAdapter.deleteVerificationByIdentifier(identifier);
    throw error;
  }

  return NextResponse.json({ success: true });
}
