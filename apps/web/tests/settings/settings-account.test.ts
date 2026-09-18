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
  assert.match(accountSection, /authClient\.changeEmail/);
  assert.match(accountSection, /authClient\.changePassword/);
  assert.match(accountSection, /deleteCurrentAccount\(/);
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
  assert.match(settingsTabs, /<AccountSection key=\{session\?\.user\.id \?\? "anonymous"\} locale=\{settings\.locale\} \/>/);
});

test("account deletion uses the server-side business-cleanup orchestrator", () => {
  const deletionService = readFileSync("features/settings/services/account-deletion.ts", "utf8");
  const authServer = readFileSync("lib/auth/server.ts", "utf8");
  assert.match(accountSection, /deleteCurrentAccount/);
  assert.match(deletionService, /\/api\/auth\/account-deletion/);
  assert.doesNotMatch(deletionService, /userId|user_id/);
  assert.match(authServer, /deleteVerificationByIdentifier\(/);
  assert.match(authServer, /setPasswordOtpIdentifier\(user\.id\)/);
});

test("email changes stay on Better Auth's confirmation and verification flow", () => {
  const authServer = readFileSync("lib/auth/server.ts", "utf8");
  assert.match(authServer, /changeEmail:\s*\{\s*enabled: true,/);
  assert.match(authServer, /sendChangeEmailConfirmation,/);
  assert.match(accountSection, /callbackURL: "\/settings\?tab=profile"/);
  assert.match(accountSection, /SENSITIVE_SESSION_REQUIRED/);
  assert.match(accountSection, /onSuccess: \(\) => submitEmailChange/);
  assert.match(accountSection, /notice: t\.reauthEmailNotice/);
});

test("sensitive account actions reauthenticate and reject an identity switch", () => {
  assert.match(accountSection, /authClient\.getSession\(\)/);
  assert.match(accountSection, /latest\.data\?\.user\.id === expectedUserId/);
  assert.match(accountSection, /reauthAccountMismatch/);
  assert.match(accountSection, /openLogin\(\{ notice: t\.reauthNotice, onSuccess: removeAccount \}\)/);
});

test("sessions panel uses Better Auth session APIs", () => {
  assert.match(accountSessions, /authClient\.listSessions/);
  assert.match(accountSessions, /authClient\.revokeOtherSessions/);
  assert.match(accountSessions, /SESSION_NOT_FRESH/);
  assert.match(accountSessions, /openLogin\(/);
  assert.match(accountSessions, /latest\.data\?\.user\.id !== currentUserId/);
  assert.doesNotMatch(readFileSync("lib/auth/server.ts", "utf8"), /freshAge:\s*0/);
});

test("account state and sessions are scoped to the active authentication identity", () => {
  assert.match(settingsTabs, /<SettingsTabsForIdentity key=\{session\?\.user\.id \?\? "anonymous"\} \/>/);
  assert.match(accountSection, /activeUserIdRef/);
  assert.match(accountSection, /\[session\?\.user\.id\]/);
  assert.match(accountSection, /activeUserIdRef\.current !== userId/);
  assert.match(settingsTabs, /<AccountSection key=\{session\?\.user\.id \?\? "anonymous"\}/);
  assert.match(accountSection, /currentUserId=\{userId\}/);
  assert.match(accountSection, /<AccountSessions/);
});
