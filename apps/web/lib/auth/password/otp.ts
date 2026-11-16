import {
  constantTimeEqual,
  generateRandomString,
  makeSignature,
} from "better-auth/crypto";

/** 设置密码专用邮箱验证码的配置。 */
export const SET_PASSWORD_OTP_LENGTH = 6;
export const SET_PASSWORD_OTP_EXPIRES_IN_SECONDS = 5 * 60;
export const SET_PASSWORD_OTP_ALLOWED_ATTEMPTS = 3;
export const SET_PASSWORD_OTP_RESEND_COOLDOWN_SECONDS = 60;

/** verification 表中存放「设置密码验证码」的 identifier。 */
export function setPasswordOtpIdentifier(userId: string): string {
  return `set-password-otp:${userId}`;
}

export function generateSetPasswordOtp(): string {
  return generateRandomString(SET_PASSWORD_OTP_LENGTH, "0-9");
}

export async function hashSetPasswordOtp(
  userId: string,
  otp: string,
  secret: string,
): Promise<string> {
  return makeSignature(`${userId}:${otp}`, secret);
}

export async function otpMatches(
  candidateHash: string,
  storedHash: string,
): Promise<boolean> {
  return constantTimeEqual(candidateHash, storedHash);
}

export interface SetPasswordOtpValue {
  otpHash: string;
  attempts: number;
  /** Unix milliseconds; omitted only for records created before resend limiting. */
  issuedAt?: number;
}

export function createSetPasswordOtpValue(
  otpHash: string,
  issuedAt = Date.now(),
): SetPasswordOtpValue {
  return { otpHash, attempts: 0, issuedAt };
}

export function canResendSetPasswordOtp(
  value: SetPasswordOtpValue,
  now = Date.now(),
): boolean {
  if (value.issuedAt === undefined) return true;
  return now - value.issuedAt >= SET_PASSWORD_OTP_RESEND_COOLDOWN_SECONDS * 1000;
}

export function parseSetPasswordOtpValue(
  value: string,
): SetPasswordOtpValue | null {
  try {
    const parsed = JSON.parse(value) as Partial<SetPasswordOtpValue>;
    if (
      typeof parsed.otpHash !== "string" ||
      typeof parsed.attempts !== "number" ||
      !Number.isInteger(parsed.attempts) ||
      parsed.attempts < 0 ||
      (parsed.issuedAt !== undefined &&
        (typeof parsed.issuedAt !== "number" ||
          !Number.isFinite(parsed.issuedAt) ||
          parsed.issuedAt < 0))
    ) {
      return null;
    }

    return parsed as SetPasswordOtpValue;
  } catch {
    return null;
  }
}
