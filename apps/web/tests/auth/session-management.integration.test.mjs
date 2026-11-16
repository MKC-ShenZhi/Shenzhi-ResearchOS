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

  const staleProfile = await auth.handler(request("/get-session", {
    cookie: firstCookie,
    method: "GET",
  }));
  assert.equal(staleProfile.status, 200);
  assert.equal((await staleProfile.json()).user.email, credentials.email);

  const staleRevoke = await auth.handler(request("/revoke-other-sessions", {
    cookie: firstCookie,
  }));
  // Better Auth 1.6.28 uses authoritative-session validation for revocation,
  // while listing additionally enforces freshness. Preserve both policies.
  assert.equal(staleRevoke.status, 200);
  assert.equal(database.session.length, 1);

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

test("session listing and revocation isolate users and reject expired or missing sessions", async () => {
  const database = { user: [], session: [], account: [], verification: [] };
  const auth = betterAuth({
    secret: TEST_SECRET,
    baseURL: BASE_URL,
    database: memoryAdapter(database),
    emailAndPassword: { enabled: true },
  });
  const cookies = [];
  for (const email of ["a@example.com", "b@example.com"]) {
    const response = await auth.handler(request("/sign-up/email", {
      body: { email, password: TEST_PASSWORD, name: email },
    }));
    assert.equal(response.status, 200);
    cookies.push(sessionCookie(response));
  }
  for (const cookie of cookies) {
    const current = await auth.handler(request("/get-session", { cookie, method: "GET" }));
    const userId = (await current.json()).user.id;
    const list = await auth.handler(request("/list-sessions", { cookie, method: "GET" }));
    assert.equal(list.status, 200);
    const sessions = await list.json();
    assert.equal(sessions.length, 1);
    assert.equal(sessions[0].userId, userId);
    const revoke = await auth.handler(request("/revoke-other-sessions", { cookie }));
    assert.equal(revoke.status, 200);
    assert.equal(database.session.length, 2, "another user's session is never revoked");
  }

  database.session[0].expiresAt = new Date(Date.now() - 1000);
  for (const cookie of [cookies[0], undefined]) {
    const current = await auth.handler(request("/get-session", { cookie, method: "GET" }));
    assert.equal(current.status, 200);
    assert.equal(await current.json(), null);
    for (const [path, method] of [["/list-sessions", "GET"], ["/revoke-other-sessions", "POST"]]) {
      const response = await auth.handler(request(path, { cookie, method }));
      assert.equal(response.status, 401);
      assert.equal((await response.json()).code, "UNAUTHORIZED");
    }
  }
  const otherUser = await auth.handler(request("/get-session", { cookie: cookies[1], method: "GET" }));
  assert.equal((await otherUser.json()).user.email, "b@example.com");
});
