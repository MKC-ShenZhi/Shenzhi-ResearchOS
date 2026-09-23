import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { chatTimestampMs, mergeHistorySources } from "../../features/chat/services/history-snapshot";
import { useAskSidebarBridge } from "../../stores/ask-sidebar-bridge";

test("formal sidebar history uses only paged Agent sessions", () => {
  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  assert.match(sidebar, /listAgentSessions\(PAGE_SIZE/);
  assert.match(sidebar, /const PAGE_SIZE = 10/);
  assert.match(sidebar, /page\.next_cursor/);
  assert.doesNotMatch(sidebar, /listChatSessions|listLocalAskSessions|mergeHistorySources|useAskSidebarBridge/);
});

test("history snapshot treats an empty backend list as authoritative", () => {
  const local = {
    id: "local_fallback",
    title: "本地问题",
    updatedAt: 20,
    turns: [],
    mode: "fast",
    model: "model",
    web_search: false,
  };
  const db = [{ id: "backend-session", title: "后端问题", updated_at: 30, favorite: false }];

  assert.deepEqual(
    mergeHistorySources([], [local]).map((item) => [item.id, item.source]),
    [["local_fallback", "local"]],
  );
  assert.deepEqual(
    mergeHistorySources(db, [local]).map((item) => [item.id, item.source]),
    [["backend-session", "db"], ["local_fallback", "local"]],
  );
});

test("backend Unix seconds are normalized to browser milliseconds", () => {
  const db = [{
    id: "backend-session",
    title: "后端问题",
    updated_at: 1_757_116_800,
    favorite: false,
  }];

  assert.equal(mergeHistorySources(db, [])[0]?.updatedAt, 1_757_116_800_000);
});

test("auth identity changes reset the Agent cursor before refetch", () => {
  const store = useAskSidebarBridge;
  const state = store.getState();
  state.setHistoryItems([{
    id: "old-session",
    title: "旧身份会话",
    updatedAt: 1,
    source: "db",
  }]);
  state.setActiveHistoryId("old-session");
  state.setActiveSessionId("old-session");
  state.requestLoad(store.getState().historyItems[0]!);

  store.getState().resetForIdentityChange();

  assert.deepEqual(store.getState().historyItems, []);
  assert.equal(store.getState().activeHistoryId, null);
  assert.equal(store.getState().activeSessionId, null);
  assert.equal(store.getState().pendingAction, null);

  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  assert.match(sidebar, /session\?\.user\.id/);
  assert.match(sidebar, /cursorRef\.current = null/);
  assert.match(sidebar, /hasMoreRef\.current = true/);
  assert.doesNotMatch(sidebar, /listLocalAskSessions|deleteLocalAskSession|chatIdentityScope/);
  assert.doesNotMatch(sidebar, /location\.reload/);
});

test("auth-owned identity scope is passed through every local-history operation", () => {
  const workspace = readFileSync("features/chat/components/agent-chat.tsx", "utf8");
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");

  assert.match(workspace, /identityScope=\{identityScope\}/);
  assert.match(workspace, /useChatSession\(\{[\s\S]*?identityScope,/);
  assert.match(hook, /upsertLocalAskSession\(identityScope,/);
  assert.match(hook, /deleteLocalAskSession\(identityScope, retiringLocalId\)/);
  assert.match(hook, /getLocalAskSession\(identityScope, pendingAction\.item\.id\)/);
  assert.doesNotMatch(hook, /useAuth\(/);
});

test("Agent delete removes the exact sidebar item and returns home for the active session", () => {
  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  assert.match(sidebar, /await deleteAgentSession\(item\.id\)/);
  assert.match(sidebar, /current\.filter\(\(entry\) => entry\.id !== item\.id\)/);
  assert.match(sidebar, /currentSessionId === item\.id\) router\.push\("\/"\)/);
});

test("backend unix seconds become millisecond timestamps for sidebar dates", () => {
  assert.equal(chatTimestampMs(1_767_686_400), 1_767_686_400_000);
  assert.equal(chatTimestampMs(1_767_686_400_000), 1_767_686_400_000);
  const [item] = mergeHistorySources(
    [{ id: "s", title: "t", updated_at: 1_767_686_400, favorite: false }],
    [],
  );
  assert.equal(new Date(item.updatedAt).getFullYear(), 2026);
});

test("non-404 delete errors remain ordinary errors", () => {
  const errors = readFileSync("features/chat/services/errors.ts", "utf8");
  assert.match(errors, /status === 404/);
  assert.doesNotMatch(errors, /status === 404 \|\| status === 500/);
});
