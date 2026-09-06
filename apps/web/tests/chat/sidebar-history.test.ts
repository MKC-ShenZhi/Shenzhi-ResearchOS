import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { mergeHistorySources } from "../../features/chat/services/history-snapshot";
import { useAskSidebarBridge } from "../../stores/ask-sidebar-bridge";

test("backend list [] replaces old DB history while preserving local fallback entries", () => {
  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  const bridge = readFileSync("stores/ask-sidebar-bridge.ts", "utf8");

  assert.match(sidebar, /setHistoryItems\(mergeHistorySources\(data\.sessions/);
  assert.doesNotMatch(sidebar, /bridgeItems\.length > 0 \? bridgeItems : fetched/);
  assert.match(bridge, /removeHistoryItem/);
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

test("auth identity changes clear the cached history selection before refetch", () => {
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
  assert.match(sidebar, /chatIdentityScope\(session\?\.user\.id\)/);
  assert.match(sidebar, /resetForIdentityChange\(\)/);
  assert.doesNotMatch(sidebar, /location\.reload/);
});

test("missing delete is idempotent and removes the exact DB item", () => {
  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  const errors = readFileSync("features/chat/services/errors.ts", "utf8");

  assert.match(errors, /export function isMissingSessionError/);
  assert.match(sidebar, /isMissingSessionError\(error\)/);
  assert.match(sidebar, /removeHistoryItem/);
});

test("non-404 delete errors remain ordinary errors", () => {
  const errors = readFileSync("features/chat/services/errors.ts", "utf8");
  assert.match(errors, /status === 404/);
  assert.doesNotMatch(errors, /status === 404 \|\| status === 500/);
});
