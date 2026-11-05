import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");

test("formal sidebar history uses only paged Agent sessions", () => {
  assert.match(sidebar, /listAgentSessions\(PAGE_SIZE/);
  assert.match(sidebar, /const PAGE_SIZE = 10/);
  assert.match(sidebar, /page\.next_cursor/);
  assert.doesNotMatch(sidebar, /listChatSessions|listLocalAskSessions|mergeHistorySources|useAskSidebarBridge/);
});

test("auth identity changes reset the Agent cursor before refetch", () => {
  assert.match(sidebar, /session\?\.user\.id/);
  assert.match(sidebar, /cursorRef\.current = null/);
  assert.match(sidebar, /hasMoreRef\.current = true/);
  assert.doesNotMatch(sidebar, /listLocalAskSessions|deleteLocalAskSession|chatIdentityScope/);
  assert.doesNotMatch(sidebar, /location\.reload/);
});

test("Agent history click is URL-only and has no local-history branch", () => {
  assert.match(sidebar, /router\.push\(`\/agents\?session=\$\{encodeURIComponent\(item\.id\)\}`\)/);
  assert.doesNotMatch(sidebar, /item\.source|askSessionUrl|listLocalAskSessions/);
});

test("Agent delete removes the exact sidebar item and returns home for the active session", () => {
  assert.match(sidebar, /await deleteAgentSession\(item\.id\)/);
  assert.match(sidebar, /current\.filter\(\(entry\) => entry\.id !== item\.id\)/);
  assert.match(sidebar, /currentSessionId === item\.id\) router\.push\("\/agents"\)/);
});
