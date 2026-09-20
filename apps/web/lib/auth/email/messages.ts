import type { User } from "better-auth";

import type { AuthEmailMessage } from "../providers/email";

export type AuthEmailUser = Pick<User, "email" | "name">;

export type EmailOtpType =
  | "sign-in"
  | "email-verification"
  | "forget-password"
  | "change-email"
  | "set-password";

const OTP_PURPOSE_LABELS: Record<EmailOtpType, string> = {
  "sign-in": "登录",
  "email-verification": "邮箱验证",
  "forget-password": "密码重置",
  "change-email": "邮箱变更",
  "set-password": "设置密码",
};

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character] ?? character,
  );
}

function formatExpiration(seconds: number): string {
  if (seconds % 60 === 0) {
    return `${seconds / 60} 分钟`;
  }

  return `${seconds} 秒`;
}

export function buildVerificationEmailMessage(input: {
  user: AuthEmailUser;
  url: string;
  newEmail?: string;
}): AuthEmailMessage {
  const displayName = input.user.name.trim() || "用户";
  const escapedName = escapeHtml(displayName);
  const escapedUrl = escapeHtml(input.url);

  if (input.newEmail) {
    const escapedNewEmail = escapeHtml(input.newEmail);
    return {
      to: input.user.email,
      subject: "确认更换你的深知邮箱",
      text: `你好，${displayName}：\n\n有人请求将你的深知账户邮箱更换为：${input.newEmail}\n请打开以下链接确认；如果不是你本人操作，请忽略此邮件：\n${input.url}`,
      html: `<p>你好，${escapedName}：</p><p>有人请求将你的深知账户邮箱更换为：<strong>${escapedNewEmail}</strong></p><p>请打开以下链接确认；如果不是你本人操作，请忽略此邮件。</p><p><a href="${escapedUrl}">确认更换邮箱</a></p>`,
    };
  }

  return {
    to: input.user.email,
    subject: "验证你的深知邮箱",
    text: `你好，${displayName}：\n\n请打开以下链接完成邮箱验证：\n${input.url}`,
    html: `<p>你好，${escapedName}：</p><p>请打开以下链接完成邮箱验证：</p><p><a href="${escapedUrl}">验证邮箱</a></p>`,
  };
}

export function buildPasswordResetEmailMessage(input: {
  user: AuthEmailUser;
  url: string;
}): AuthEmailMessage {
  const displayName = input.user.name.trim() || "用户";
  const escapedName = escapeHtml(displayName);
  const escapedUrl = escapeHtml(input.url);

  return {
    to: input.user.email,
    subject: "重置你的深知密码",
    text: `你好，${displayName}：\n\n请打开以下链接重置密码：\n${input.url}\n\n如果不是你本人操作，可以忽略这封邮件。`,
    html: `<p>你好，${escapedName}：</p><p>请打开以下链接重置密码：</p><p><a href="${escapedUrl}">重置密码</a></p><p>如果不是你本人操作，可以忽略这封邮件。</p>`,
  };
}

export function buildEmailOtpMessage(input: {
  email: string;
  otp: string;
  type: EmailOtpType;
  expiresInSeconds?: number;
}): AuthEmailMessage {
  const expiresInSeconds = input.expiresInSeconds ?? 300;
  const purpose = OTP_PURPOSE_LABELS[input.type];
  const escapedOtp = escapeHtml(input.otp);
  const expiration = formatExpiration(expiresInSeconds);

  return {
    to: input.email,
    subject: "你的深知验证码",
    text: `你的${purpose}验证码是：${input.otp}\n\n验证码${expiration}内有效。请勿将验证码告知他人。`,
    html: `<p>你的${purpose}验证码是：</p><p><strong>${escapedOtp}</strong></p><p>验证码${expiration}内有效。请勿将验证码告知他人。</p>`,
  };
}
