import assert from "node:assert/strict";
import test from "node:test";

import { NextRequest } from "next/server";

import * as identity from "../../clients/backend/identity";
import { forwardToBusinessBackend } from "../../clients/backend/forward";

function request(requestId?: string, range?: string, idempotencyKey?: string) {
  const headers = new Headers();
  if (requestId) headers.set("X-Request-ID", requestId);
  if (range) headers.set("Range", range);
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  return new NextRequest("http://web.test/api/v1/health", {
    headers,
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

test("V1 BFF rejects retired Agent submissions", async () => {
  const response = await forwardToBusinessBackend(
    request("trace-request-1", undefined, "agent-operation-1"),
    "http://backend.test",
    ["agent", "sessions"],
  );

  assert.equal(response.status, 404);
});

test("BFF forwards Agent requests to the V2 Backend path", async (t) => {
  t.mock.method(identity, "resolveBackendIdentity", async () => ({ kind: "anonymous" }));
  let target = "";
  t.mock.method(globalThis, "fetch", async (url: string) => {
    target = String(url);
    return new Response(null, { status: 204 });
  });

  const response = await forwardToBusinessBackend(
    request("agent-v2-1"), "http://backend.test", ["agent", "sessions"], "v2",
  );

  assert.equal(target, "http://backend.test/api/v2/agent/sessions");
  assert.equal(response.status, 204);
});

test("V2 BFF rejects internal and non-Agent paths before identity resolution", async () => {
  for (const path of [
    ["agent", "internal", "protocol-capabilities"],
    ["agent", "%69nternal", "task-metering-bindings"],
    ["agent", "%2569nternal", "task-metering-bindings"],
    ["admin-console", "users"],
    ["knowledge", "papers"],
  ]) {
    const response = await forwardToBusinessBackend(
      {} as NextRequest, "invalid-origin", path, "v2",
    );
    assert.equal(response.status, 404);
  }
});

test("V1 BFF rejects retired Agent product paths before identity resolution", async () => {
  const response = await forwardToBusinessBackend(
    {} as NextRequest, "invalid-origin", ["agent", "sessions"], "v1",
  );
  assert.equal(response.status, 404);
});

test("V1 BFF serves historical Agent assets through the V2 read routes", async (t) => {
  t.mock.method(identity, "resolveBackendIdentity", async () => ({ kind: "anonymous" }));
  const targets: string[] = [];
  t.mock.method(globalThis, "fetch", async (url: string) => {
    targets.push(url);
    return new Response("chart", { headers: { "content-type": "image/png" } });
  });

  const asset = await forwardToBusinessBackend(
    request(), "http://backend.test", ["agent", "assets", "ses_1", "figures", "旧 图.png"],
  );
  const file = await forwardToBusinessBackend(
    new NextRequest("http://web.test/api/v1/agent/session/_/file?path=figures%2Fchart.png"),
    "http://backend.test",
    ["agent", "session", "_", "file"],
  );
  const post = await forwardToBusinessBackend(
    new NextRequest("http://web.test", { method: "POST" }),
    "http://backend.test",
    ["agent", "assets", "ses_1", "figures", "chart.png"],
  );

  assert.deepEqual(targets, [
    "http://backend.test/api/v2/agent/assets/ses_1/figures/%E6%97%A7%20%E5%9B%BE.png",
    "http://backend.test/api/v2/agent/session/_/file?path=figures%2Fchart.png",
  ]);
  assert.equal(asset.status, 200);
  assert.equal(asset.headers.get("content-type"), "image/png");
  assert.equal(await asset.text(), "chart");
  assert.equal(file.status, 200);
  assert.equal(post.status, 404);
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

test("BFF forwards PDF Range and preserves partial response and filename headers", async (t) => {
  t.mock.method(identity, "resolveBackendIdentity", async () => ({ kind: "anonymous" }));
  let outgoingHeaders: Headers | undefined;
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    outgoingHeaders = new Headers(init.headers);
    return new Response("pdf", {
      status: 206,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Range": "bytes 0-2/3",
        "Content-Disposition": "inline; filename=paper.pdf; filename*=UTF-8''%E8%AE%BA%E6%96%87.pdf",
      },
    });
  });

  const response = await forwardToBusinessBackend(
    request(undefined, "bytes=0-2"),
    "http://backend.test",
    ["paper-resource", "pdf"],
  );

  assert.equal(outgoingHeaders?.get("range"), "bytes=0-2");
  assert.equal(response.status, 206);
  assert.equal(response.headers.get("content-range"), "bytes 0-2/3");
  assert.equal(response.headers.get("content-disposition"),
    "inline; filename=paper.pdf; filename*=UTF-8''%E8%AE%BA%E6%96%87.pdf");
});
