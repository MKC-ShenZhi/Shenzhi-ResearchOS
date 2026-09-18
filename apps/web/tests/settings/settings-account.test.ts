import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const accountSection = readFileSync("features/settings/components/account-section.tsx", "utf8");
const accountSessions = readFileSync("features/settings/components/account-sessions.tsx", "utf8");
const accountPassword = readFileSync("features/settings/services/account-password.ts", "utf8");
const settingsTabs = readFileSync("features/settings/components/settings-tabs.tsx", "utf8");
const i18n = readFileSync("features/settings/i18n.ts", "utf8");

test("account section stays on Better Auth and does not call FastAPI clients", () => {
  assert.match(accountSection, /authClient\.updateUser/);
  assert.match(accountSection, /authClient\.changePassword/);
  assert.match(accountSection, /deleteAccount\(/);
  assert.doesNotMatch(accountSection, /apiJson|api\/v1\/(profile|settings)/);
  assert.doesNotMatch(accountSection, /getUserProfile|patchUserProfile|getUserSettings/);
  assert.match(accountSection, /locale: SettingsLocale/);
});

test("account password OTP flows use the settings service boundary", () => {
  assert.match(accountSection, /sendSetPasswordOtp/);
  assert.match(accountSection, /setPasswordWithOtp/);
  assert.match(accountPassword, /\/api\/auth\/password\/send-otp/);
  assert.match(accountPassword, /\/api\/auth\/password\/set/);
  assert.doesNotMatch(accountPassword, /clients\//);
});

test("account section rejects reusing the current password", () => {
  assert.match(accountSection, /newPassword === currentPassword/);
  assert.match(i18n, /samePassword/);
});

test("account UI supports bilingual delete confirmation", () => {
  assert.match(i18n, /deleteConfirmPhrase: "注销账号"/);
  assert.match(i18n, /deleteConfirmPhrase: "Delete account"/);
  assert.match(accountSection, /deleteConfirmation !== t\.deleteConfirmPhrase/);
});

test("settings passes locale into the account section", () => {
  assert.match(settingsTabs, /<AccountSection locale=\{settings\.locale\} \/>/);
});

test("sessions panel uses Better Auth session APIs", () => {
  assert.match(accountSessions, /authClient\.listSessions/);
  assert.match(accountSessions, /authClient\.revokeOtherSessions/);
});
