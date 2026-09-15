import assert from "node:assert/strict";
import test from "node:test";

import {
  createRequestId,
  normalizeRequestId,
  resolveRequestId,
} from "../../lib/observability/request-id";
import { logInfo } from "../../lib/observability/logger";

test("request ID helpers normalize safe values and generate UUIDs", () => {
  assert.equal(normalizeRequestId("  request-123  "), "request-123");
  assert.equal(normalizeRequestId("contains whitespace"), undefined);
  assert.equal(normalizeRequestId(""), undefined);
  assert.equal(normalizeRequestId("a".repeat(129)), undefined);
  assert.match(createRequestId(), /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  assert.equal(resolveRequestId("request-123"), "request-123");
  assert.match(resolveRequestId(undefined), /^[0-9a-f-]{36}$/i);
});

test("web logger emits one JSON line with only allowlisted fields", () => {
  const lines: string[] = [];
  const originalInfo = console.info;
  console.info = (line: string) => lines.push(line);

  try {
    logInfo("test.event", {
      request_id: "request-123",
      route: "/health",
      status_code: 200,
      secret: "must-not-be-logged",
    } as never);
  } finally {
    console.info = originalInfo;
  }

  assert.equal(lines.length, 1);
  const record = JSON.parse(lines[0]);
  assert.equal(record.event, "test.event");
  assert.equal(record.request_id, "request-123");
  assert.equal(record.route, "/health");
  assert.equal(record.status_code, 200);
  assert.equal(record.secret, undefined);
  assert.equal(record.service, "web");
});
