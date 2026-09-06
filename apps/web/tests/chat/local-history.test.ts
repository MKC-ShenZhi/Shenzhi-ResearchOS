import assert from "node:assert/strict";
import test, { beforeEach } from "node:test";

import { mergeHistorySources } from "../../features/chat/services/history-snapshot";
import { chatIdentityScope } from "../../features/chat/services/identity-scope";
import {
  deleteLocalAskSession,
  getLocalAskSession,
  listLocalAskSessions,
  upsertLocalAskSession,
  type LocalAskSession,
} from "../../features/chat/services/local-history";
import { useAskSidebarBridge } from "../../stores/ask-sidebar-bridge";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

const storage = new MemoryStorage();
Object.defineProperty(globalThis, "window", { value: globalThis, configurable: true });
Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });

const anonymous = chatIdentityScope(undefined);
const userA = chatIdentityScope("A");
const userB = chatIdentityScope("B");

function localSession(id: string, updatedAt = Date.now()): LocalAskSession {
  return {
    id,
    title: `问题 ${id}`,
    updatedAt,
    turns: [],
    mode: "fast",
    model: "model",
    web_search: false,
  };
}

beforeEach(() => {
  storage.clear();
  useAskSidebarBridge.getState().resetForIdentityChange();
});

test("anonymous local history is not visible to user A", () => {
  upsertLocalAskSession(anonymous, localSession("anonymous-fallback"));

  assert.deepEqual(listLocalAskSessions(userA), []);
  assert.equal(getLocalAskSession(userA, "anonymous-fallback"), null);
});

test("user A local history is not visible anonymously", () => {
  upsertLocalAskSession(userA, localSession("user-a-fallback"));

  assert.deepEqual(listLocalAskSessions(anonymous), []);
  assert.equal(getLocalAskSession(anonymous, "user-a-fallback"), null);
});

test("user A local history is not visible to user B", () => {
  upsertLocalAskSession(userA, localSession("user-a-fallback"));

  assert.deepEqual(listLocalAskSessions(userB), []);
  assert.equal(getLocalAskSession(userB, "user-a-fallback"), null);
});

test("user A logout and user B refresh cannot restore A local history into the bridge", () => {
  const bridge = useAskSidebarBridge;
  const item = localSession("user-a-fallback");
  upsertLocalAskSession(userA, item);
  bridge.getState().setHistoryItems(mergeHistorySources([], listLocalAskSessions(userA)));
  bridge.getState().setActiveHistoryId(item.id);
  bridge.getState().setActiveSessionId(item.id);
  bridge.getState().requestLoad(bridge.getState().historyItems[0]!);

  bridge.getState().resetForIdentityChange();
  assert.deepEqual(bridge.getState().historyItems, []);
  assert.equal(bridge.getState().activeHistoryId, null);
  assert.equal(bridge.getState().activeSessionId, null);
  assert.equal(bridge.getState().pendingAction, null);

  bridge.getState().setHistoryItems(mergeHistorySources([], listLocalAskSessions(anonymous)));
  assert.deepEqual(bridge.getState().historyItems, []);
  bridge.getState().resetForIdentityChange();
  bridge.getState().setHistoryItems(mergeHistorySources([], listLocalAskSessions(userB)));
  assert.deepEqual(bridge.getState().historyItems, []);
});

test("user A can read its unexpired local fallback after logging in again", () => {
  upsertLocalAskSession(userA, localSession("user-a-fallback"));

  assert.deepEqual(listLocalAskSessions(anonymous), []);
  assert.deepEqual(listLocalAskSessions(userB), []);
  assert.equal(listLocalAskSessions(userA)[0]?.id, "user-a-fallback");
});

test("same-scope TTL, maximum, merge, get, upsert, and delete behavior is preserved", () => {
  const now = Date.now();
  storage.setItem(
    "shenzhi.ask.local-sessions:user:A",
    JSON.stringify([
      localSession("expired", now - 24 * 60 * 60 * 1000 - 1),
      localSession("live", now),
    ]),
  );

  assert.deepEqual(listLocalAskSessions(userA).map((session) => session.id), ["live"]);
  assert.deepEqual(
    JSON.parse(storage.getItem("shenzhi.ask.local-sessions:user:A") ?? "[]")
      .map((session: LocalAskSession) => session.id),
    ["live"],
  );

  upsertLocalAskSession(userA, { ...localSession("live", now + 1), title: "更新后的标题" });
  assert.equal(getLocalAskSession(userA, "live")?.title, "更新后的标题");
  assert.deepEqual(
    mergeHistorySources(
      [{ id: "backend", title: "后端", updated_at: Math.ceil((now + 2) / 1000), favorite: false }],
      listLocalAskSessions(userA),
    ).map((item) => item.source),
    ["db", "local"],
  );

  deleteLocalAskSession(userA, "live");
  assert.equal(getLocalAskSession(userA, "live"), null);

  for (let index = 0; index < 35; index += 1) {
    upsertLocalAskSession(userA, localSession(`session-${index}`, now + index));
  }
  const capped = listLocalAskSessions(userA);
  assert.equal(capped.length, 30);
  assert.equal(capped[0]?.id, "session-34");
  assert.equal(capped.at(-1)?.id, "session-5");
});

test("legacy unscoped storage is not assigned to any identity", () => {
  storage.setItem("shenzhi.ask.local-sessions", JSON.stringify([localSession("legacy")]));

  assert.deepEqual(listLocalAskSessions(anonymous), []);
  assert.deepEqual(listLocalAskSessions(userA), []);
  assert.deepEqual(listLocalAskSessions(userB), []);
});
