import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import * as sessionUrl from "../../features/chat/services/session-url";
import {
  askSessionUrl,
  normalizeAskSessionId,
} from "../../features/chat/services/session-url";

function withWindowSearch(search: string, callback: () => void) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { search } },
  });
  try {
    callback();
  } finally {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  }
}

test("legacy ask route redirects to the Discover entry", () => {
  const route = readFileSync("app/agents/ask/page.tsx", "utf8");
  assert.match(route, /redirect\("\/"\)/);
  assert.doesNotMatch(route, /AskPage/);
});

test("session URLs use the ask route and preserve opaque IDs", () => {
  const source = readFileSync("features/chat/services/session-url.ts", "utf8");
  assert.match(source, /export function askSessionUrl/);
  assert.match(source, /encodeURIComponent/);
  assert.match(source, /agents\/ask/);
});

test("session URL helpers preserve opaque IDs and reject unusable values", () => {
  assert.equal(normalizeAskSessionId(" opaque/id?value=1 "), "opaque/id?value=1");
  assert.equal(askSessionUrl("opaque/id?value=1"), "/agents/ask?session=opaque%2Fid%3Fvalue%3D1");
  assert.equal(askSessionUrl(null), "/agents/ask");
  assert.equal(normalizeAskSessionId("   "), null);
  assert.equal(normalizeAskSessionId("bad\nvalue"), null);
  assert.equal(normalizeAskSessionId("x".repeat(201)), null);
});

test("readCurrentSessionId is SSR-safe and reads the browser URL", () => {
  const readCurrentSessionId = (sessionUrl as unknown as {
    readCurrentSessionId?: (search?: string) => string | null;
  }).readCurrentSessionId;

  assert.equal(typeof readCurrentSessionId, "function");
  assert.equal(readCurrentSessionId?.(), null);
  assert.equal(readCurrentSessionId?.("?session=opaque%2Fid"), "opaque/id");

  withWindowSearch("?session=opaque%2Fid%3Fvalue%3D1", () => {
    assert.equal(readCurrentSessionId?.(), "opaque/id?value=1");
  });
});
