import assert from "node:assert/strict";
import test from "node:test";

import { requiresEmailDelivery } from "../../lib/auth/email/requirements.js";
import { EMAIL_OTP_OPTIONS } from "../../lib/auth/email/options.js";

test("stores Email OTP values as Better Auth hashes", () => {
  assert.equal(EMAIL_OTP_OPTIONS.storeOTP, "hashed");
});

test("prevents Email OTP sign-in from creating accounts", () => {
  assert.equal(EMAIL_OTP_OPTIONS.disableSignUp, true);
});

test("keeps the existing OTP length, expiry, and attempt limit", () => {
  assert.equal(EMAIL_OTP_OPTIONS.otpLength, 6);
  assert.equal(EMAIL_OTP_OPTIONS.expiresIn, 300);
  assert.equal(EMAIL_OTP_OPTIONS.allowedAttempts, 3);
});

test("pre-verified email/password sign-up sends no second message", () => {
  assert.equal(requiresEmailDelivery("/sign-up/email"), false);
});

test("missing-provider guard does not block password or Email OTP login", () => {
  assert.equal(requiresEmailDelivery("/sign-in/email"), false);
  assert.equal(requiresEmailDelivery("/sign-in/email-otp"), false);
});

test("mail-delivery endpoints remain guarded when they actually send mail", () => {
  assert.equal(requiresEmailDelivery("/send-verification-email"), true);
  assert.equal(requiresEmailDelivery("/request-password-reset"), true);
  assert.equal(
    requiresEmailDelivery("/email-otp/send-verification-otp"),
    true,
  );
  assert.equal(
    requiresEmailDelivery("/registration-email/send-otp"),
    true,
  );
  assert.equal(requiresEmailDelivery("/change-email"), true);
});
