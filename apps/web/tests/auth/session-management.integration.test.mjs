import assert from "node:assert/strict";
import test from "node:test";

import { memoryAdapter } from "better-auth/adapters/memory";
import { betterAuth } from "better-auth";

const BASE_URL = "http://localhost:3000";
const TEST_SECRET = "test-secret-that-is-at-least-thirty-two-characters";
const TEST_PASSWORD = "Password12345";

function request(path, { body, cookie, method = "POST" } = {}) {
  return new Request(`${BASE_URL}/api/auth${path}`, {
    method,
    headers: {
      origin: BASE_URL,
      ...(body ? { "content-type": "application/json" } : {}),
      ...(cookie ? { cookie } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
}

function sessionCookie(response) {
  const cookie = response.headers.get("set-cookie")?.split(";")[0];
  assert.ok(cookie);
  return cookie;
}

test("stale session reauthentication restores listing and revoke keeps the current session", async () => {
  const database = { user: [], session: [], account: [], verification: [] };
  const auth = betterAuth({
    secret: TEST_SECRET,
    baseURL: BASE_URL,
    database: memoryAdapter(database),
    emailAndPassword: { enabled: true },
    session: { freshAge: 60 },
  });
  const credentials = {
    email: "sessions@example.com",
    password: TEST_PASSWORD,
  };

  const firstSignIn = await auth.handler(request("/sign-up/email", {
    body: { ...credentials, name: "Session test" },
  }));
  assert.equal(firstSignIn.status, 200);
  const firstCookie = sessionCookie(firstSignIn);
  database.session[0].createdAt = new Date(Date.now() - 61_000);

  const staleList = await auth.handler(request("/list-sessions", {
    cookie: firstCookie,
    method: "GET",
  }));
  assert.equal(staleList.status, 403);
  assert.equal((await staleList.json()).code, "SESSION_NOT_FRESH");

  const secondSignIn = await auth.handler(request("/sign-in/email", {
    body: credentials,
  }));
  assert.equal(secondSignIn.status, 200);
  const secondCookie = sessionCookie(secondSignIn);

  const freshList = await auth.handler(request("/list-sessions", {
    cookie: secondCookie,
    method: "GET",
  }));
  assert.equal(freshList.status, 200);
  assert.equal((await freshList.json()).length, 2);

  const revoke = await auth.handler(request("/revoke-other-sessions", {
    cookie: secondCookie,
  }));
  assert.equal(revoke.status, 200, await revoke.text());

  const remaining = await auth.handler(request("/list-sessions", {
    cookie: secondCookie,
    method: "GET",
  }));
  assert.equal(remaining.status, 200);
  const sessions = await remaining.json();
  assert.equal(sessions.length, 1);

  const currentSession = await auth.handler(request("/get-session", {
    cookie: secondCookie,
    method: "GET",
  }));
  assert.equal(currentSession.status, 200);
  assert.equal((await currentSession.json()).user.email, credentials.email);

  const revokedSession = await auth.handler(request("/get-session", {
    cookie: firstCookie,
    method: "GET",
  }));
  assert.equal(revokedSession.status, 200);
  assert.equal(await revokedSession.json(), null);
});
