import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const ROUTE_SOURCE = readFileSync(
  resolve(process.cwd(), "app/api/chat/anonymous-claim/route.ts"),
  "utf8",
);

test("anonymous-claim uses the shared request ID helper on both upstream calls", () => {
  assert.match(ROUTE_SOURCE, /REQUEST_ID_HEADER,\s*\n\s*resolveRequestId/);
  assert.match(ROUTE_SOURCE, /headers\.set\(REQUEST_ID_HEADER, requestId\)/);
  assert.match(ROUTE_SOURCE, /withRequestId\(response: NextResponse, requestId: string\)/);
  assert.equal(
    (ROUTE_SOURCE.match(/const requestId = resolveRequestId\(request\.headers\.get\(REQUEST_ID_HEADER\)\)/g) ?? []).length,
    2,
  );
});
