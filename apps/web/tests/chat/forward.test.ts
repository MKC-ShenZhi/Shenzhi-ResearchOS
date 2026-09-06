import assert from "node:assert/strict";
import test from "node:test";

import { NextRequest } from "next/server";

import * as identity from "../../clients/backend/identity";
import { forwardToBusinessBackend } from "../../clients/backend/forward";

function request(requestId?: string) {
  return new NextRequest("http://web.test/api/v1/health", {
    headers: requestId ? { "X-Request-ID": requestId } : undefined,
  });
}

test("BFF forwards and returns the same request ID", async (t) => {
  t.mock.method(identity, "resolveBackendIdentity", async () => ({ kind: "anonymous" }));

  let outgoingHeaders: Headers | undefined;
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    outgoingHeaders = new Headers(init.headers);
    return new Response(null, { status: 204 });
  });

  const response = await forwardToBusinessBackend(
    request("request-forward-1"),
    "http://backend.test",
    ["health"],
  );

  assert.equal(outgoingHeaders?.get("X-Request-ID"), "request-forward-1");
  assert.equal(response.headers.get("X-Request-ID"), "request-forward-1");
});

test("BFF generates a request ID for a missing incoming ID", async (t) => {
  t.mock.method(identity, "resolveBackendIdentity", async () => ({ kind: "anonymous" }));
  let outgoingHeaders: Headers | undefined;
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    outgoingHeaders = new Headers(init.headers);
    return new Response(null, { status: 204 });
  });

  const response = await forwardToBusinessBackend(request(), "http://backend.test", ["health"]);
  const requestId = outgoingHeaders?.get("X-Request-ID");

  assert.ok(requestId);
  assert.equal(response.headers.get("X-Request-ID"), requestId);
});

test("BFF replaces an invalid incoming request ID", async (t) => {
  t.mock.method(identity, "resolveBackendIdentity", async () => ({ kind: "anonymous" }));
  let outgoingHeaders: Headers | undefined;
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    outgoingHeaders = new Headers(init.headers);
    return new Response(null, { status: 204 });
  });

  const response = await forwardToBusinessBackend(
    request("invalid request id"),
    "http://backend.test",
    ["health"],
  );
  const requestId = outgoingHeaders?.get("X-Request-ID");

  assert.ok(requestId);
  assert.notEqual(requestId, "invalid request id");
  assert.match(requestId, /^[0-9a-f-]{36}$/i);
  assert.equal(response.headers.get("X-Request-ID"), requestId);
});

test("BFF logs a failed backend fetch with request ID but no error message", async (t) => {
  t.mock.method(identity, "resolveBackendIdentity", async () => ({ kind: "anonymous" }));
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("authorization=secret-value");
  });
  const lines: string[] = [];
  const originalError = console.error;
  console.error = (line: string) => lines.push(line);

  try {
    const response = await forwardToBusinessBackend(
      request("request-failed-1"),
      "http://backend.test",
      ["health"],
    );
    assert.equal(response.status, 503);
    assert.equal(response.headers.get("X-Request-ID"), "request-failed-1");
  } finally {
    console.error = originalError;
  }

  const record = JSON.parse(lines[0]);
  assert.equal(record.event, "bff.backend.failed");
  assert.equal(record.request_id, "request-failed-1");
  assert.equal(record.method, "GET");
  assert.equal(record.route, "/api/v1/health");
  assert.equal(record.error_type, "Error");
  assert.equal(record.message, undefined);
  assert.equal(record.authorization, undefined);
});
