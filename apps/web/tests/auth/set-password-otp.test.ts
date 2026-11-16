import assert from "node:assert/strict";
import test from "node:test";

import {
  canResendSetPasswordOtp,
  createSetPasswordOtpValue,
  parseSetPasswordOtpValue,
  SET_PASSWORD_OTP_RESEND_COOLDOWN_SECONDS,
} from "../../lib/auth/password/otp.js";

test("set-password OTP enforces a server-side resend cooldown", () => {
  const issuedAt = 1_700_000_000_000;
  const value = createSetPasswordOtpValue("hashed-otp", issuedAt);

  assert.equal(canResendSetPasswordOtp(value, issuedAt + 59_999), false);
  assert.equal(
    canResendSetPasswordOtp(
      value,
      issuedAt + SET_PASSWORD_OTP_RESEND_COOLDOWN_SECONDS * 1000,
    ),
    true,
  );
});

test("set-password OTP accepts legacy records but rejects malformed issuedAt", () => {
  assert.deepEqual(
    parseSetPasswordOtpValue(JSON.stringify({ otpHash: "legacy", attempts: 0 })),
    { otpHash: "legacy", attempts: 0 },
  );
  assert.equal(
    parseSetPasswordOtpValue(
      JSON.stringify({ otpHash: "hash", attempts: 0, issuedAt: "now" }),
    ),
    null,
  );
});
