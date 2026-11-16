import { REGISTRATION_EMAIL_SEND_OTP_PATH } from "../registration/constants";

const EMAIL_DELIVERY_PATHS = new Set([
  "/send-verification-email",
  "/request-password-reset",
  "/email-otp/send-verification-otp",
  "/email-otp/request-password-reset",
  "/forget-password/email-otp",
  "/email-otp/request-email-change",
  // Better Auth's built-in change-email flow sends a confirmation to the
  // current mailbox and a verification link to the replacement mailbox.
  "/change-email",
  REGISTRATION_EMAIL_SEND_OTP_PATH,
]);

export function requiresEmailDelivery(
  path: string,
): boolean {
  return EMAIL_DELIVERY_PATHS.has(path);
}
