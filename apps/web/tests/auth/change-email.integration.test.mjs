import assert from "node:assert/strict";
import test from "node:test";

import { memoryAdapter } from "better-auth/adapters/memory";
import { betterAuth } from "better-auth";

const BASE_URL = "http://localhost:3000";
const TEST_SECRET = "test-secret-that-is-at-least-thirty-two-characters";
const TEST_PASSWORD = "Password12345";

function request(path, options = {}) {
  return new Request(`${BASE_URL}/api/auth${path}`, {
    method: options.method ?? "POST",
    headers: {
      origin: BASE_URL,
      ...(options.body ? { "content-type": "application/json" } : {}),
      ...(options.cookie ? { cookie: options.cookie } : {}),
    },
    ...(options.body ? { body: JSON.stringify(options.body) } : {}),
  });
}

function createChangeEmailAuth() {
  const database = { user: [], session: [], account: [], verification: [] };
  const sent = [];
  const auth = betterAuth({
    secret: TEST_SECRET,
    baseURL: BASE_URL,
    database: memoryAdapter(database),
    emailAndPassword: { enabled: true },
    emailVerification: {
      async sendVerificationEmail(data) {
        sent.push({ ...data });
      },
    },
    user: {
      changeEmail: {
        enabled: true,
        async sendChangeEmailConfirmation(data) {
          sent.push({ ...data });
        },
      },
    },
  });
  return { auth, database, sent };
}

test("verified accounts change email only after current-email confirmation and new-email verification", async () => {
  const { auth, database, sent } = createChangeEmailAuth();
  const oldEmail = "old@example.com";
  const newEmail = "new@example.com";
  const signUpResponse = await auth.handler(
    request("/sign-up/email", {
      body: { name: "测试用户", email: oldEmail, password: TEST_PASSWORD },
    }),
  );
  assert.equal(signUpResponse.status, 200);
  const sessionCookie = signUpResponse.headers.get("set-cookie")?.split(";")[0];
  assert.ok(sessionCookie);
  database.user[0].emailVerified = true;

  const requestChange = await auth.handler(
    request("/change-email", {
      cookie: sessionCookie,
      body: { newEmail, callbackURL: "/settings?tab=profile" },
    }),
  );
  assert.equal(requestChange.status, 200, await requestChange.text());
  assert.equal(database.user[0].email, oldEmail);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].user.email, oldEmail);
  assert.equal(sent[0].newEmail, newEmail);

  const currentEmailConfirmation = await auth.handler(new Request(sent[0].url));
  assert.equal(currentEmailConfirmation.status, 302);
  assert.equal(database.user[0].email, oldEmail);
  assert.equal(sent.length, 2);
  assert.equal(sent[1].user.email, newEmail);
  assert.equal(sent[1].newEmail, undefined);

  const newEmailVerification = await auth.handler(new Request(sent[1].url));
  assert.equal(newEmailVerification.status, 302);
  assert.equal(database.user[0].email, newEmail);
  assert.equal(database.user[0].emailVerified, true);
});
