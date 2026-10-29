import assert from "node:assert/strict";
import test from "node:test";

import { InfiniteQueryObserver, QueryClient, type InfiniteData } from "@tanstack/react-query";
import {
  fetchHomeFeedPage,
  RecommendationFeedExpiredError,
  type DiscoveryFeedPage,
} from "../../features/search/services/discovery-feed.js";
import { recordPaperBehavior, recordSearchSubmit } from "../../clients/backend/behavior.js";
import { ActiveReadTracker } from "../../features/papers/active-read-tracker.js";

const paper = {
  id: "paper:1", title: "Paper one", abstract: "Abstract",
  authors: ["Author"], year: 2026, venue: "ACL",
  pdf_url: null, thumbnail_url: null,
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(status === 200
    ? { code: 0, data }
    : { code: 20004, message: "unavailable" }), {
    status, headers: { "Content-Type": "application/json" },
  });
}

test("authenticated home feed preserves recommendation attribution and nullable year", async () => {
  const original = globalThis.fetch;
  const requested: string[] = [];
  globalThis.fetch = async (input) => {
    requested.push(String(input));
    return json({
      items: [{ ...paper, year: null, reason: "与你关注的主题相匹配",
        sources: ["followed_topic"], request_id: "request-1", rank: 1 }],
      next_cursor: "request-1:1", has_more: true,
      request_id: "request-1", total: 2, algorithm_version: "content-v1",
    });
  };
  try {
    const page = await fetchHomeFeedPage(null, "user-a");
    assert.equal(page.items[0].date, "年份未知");
    assert.equal(page.items[0].recommendationRequestId, "request-1");
    assert.equal(page.items[0].recommendationRank, 1);
    assert.equal(page.items[0].recommendationReason, "与你关注的主题相匹配");
    assert.equal(page.nextCursor, "request-1:1");
    assert.match(requested[0], /\/recommendations\/papers\?limit=12/);
  } finally {
    globalThis.fetch = original;
  }
});

test("recommendation failure falls back to the existing discovery cursor", async () => {
  const original = globalThis.fetch;
  const requested: string[] = [];
  globalThis.fetch = async (input) => {
    const url = String(input);
    requested.push(url);
    if (url.includes("/recommendations/")) return json(null, 503);
    return json({ items: [paper], next_cursor: "daily-1", has_more: true,
      snapshot_id: "global-snapshot", total: 300 });
  };
  try {
    const first = await fetchHomeFeedPage(null, "user-a");
    assert.equal(first.items[0].id, "paper:1");
    assert.equal(first.nextCursor, "discovery:daily-1");
    await fetchHomeFeedPage(first.nextCursor, "user-a");
    assert.equal(requested.filter((url) => url.includes("/recommendations/")).length, 1);
    assert.match(requested[2], /\/discovery\/papers\?limit=12&cursor=daily-1/);
  } finally {
    globalThis.fetch = original;
  }
});

test("anonymous home feed only requests discovery", async () => {
  const original = globalThis.fetch;
  const requested: string[] = [];
  globalThis.fetch = async (input) => {
    requested.push(String(input));
    return json({ items: [paper], next_cursor: null, has_more: false,
      snapshot_id: "global-snapshot", total: 1 });
  };
  try {
    const page = await fetchHomeFeedPage(null, null);
    assert.equal(page.items.length, 1);
    assert.equal(requested.length, 1);
    assert.match(requested[0], /\/discovery\/papers/);
  } finally {
    globalThis.fetch = original;
  }
});

test("search submit and result click share a query id", async () => {
  const original = globalThis.fetch;
  const events: Array<Record<string, unknown>> = [];
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(String(init?.body));
    events.push(body.events[0]);
    return json({ inserted: 1 });
  };
  try {
    const queryId = recordSearchSubmit("RAG", "user-a");
    assert.ok(queryId);
    recordPaperBehavior({
      userId: "user-a", eventType: "search_result_click", paperId: "paper:1", source: "search",
      rank: 1, queryId,
    });
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.equal(events.length, 2);
    assert.equal(events[0].query_id, queryId);
    assert.equal(events[0].event_id, queryId);
    assert.equal(events[1].query_id, queryId);
  } finally {
    globalThis.fetch = original;
  }
});

test("abstract expansion sends a single positive-intent event", async () => {
  const original = globalThis.fetch;
  const events: Array<Record<string, unknown>> = [];
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(String(init?.body));
    events.push(body.events[0]);
    return json({ inserted: 1 });
  };
  try {
    recordPaperBehavior({
      userId: "user-a", eventType: "abstract_expand", paperId: "paper:1", source: "search",
    });
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.equal(events.length, 1);
    assert.equal(events[0].event_type, "abstract_expand");
    assert.equal(events[0].paper_id, "paper:1");
    assert.equal(events[0].source, "search");
  } finally {
    globalThis.fetch = original;
  }
});

test("active-read duration is serialized as whole seconds for the backend schema", async () => {
  const original = globalThis.fetch;
  let event: Record<string, unknown> | undefined;
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(String(init?.body));
    event = body.events[0];
    return json({ inserted: 1 });
  };
  try {
    recordPaperBehavior({
      userId: "user-a", eventType: "active_read", paperId: "paper:1", source: "paper_detail",
      durationSeconds: 30.125,
    });
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.equal(event?.duration_seconds, 30);
    assert.equal(Number.isInteger(event?.duration_seconds), true);
  } finally {
    globalThis.fetch = original;
  }
});

test("active reading accumulates foreground time across interruptions and reports once", () => {
  const tracker = new ActiveReadTracker();
  assert.equal(tracker.tick("user-1", "paper:1", true, 0), null);
  assert.equal(tracker.tick("user-1", "paper:1", true, 10_000), null);
  assert.equal(tracker.tick("user-1", "paper:1", false, 15_000), null);
  assert.equal(tracker.tick("user-1", "paper:1", false, 35_000), null);
  assert.equal(tracker.tick("user-1", "paper:1", true, 40_000), null);
  assert.equal(tracker.tick("user-1", "paper:1", true, 55_000), 30);
  assert.equal(tracker.tick("user-1", "paper:1", true, 60_000), null);
});

test("active reading tracker resets for a different paper or user", () => {
  const tracker = new ActiveReadTracker();
  assert.equal(tracker.tick("user-1", "paper:1", true, 0), null);
  assert.equal(tracker.tick("user-1", "paper:1", true, 25_000), null);
  assert.equal(tracker.tick("user-1", "paper:2", true, 30_000), null);
  assert.equal(tracker.tick("user-2", "paper:2", true, 35_000), null);
  assert.equal(tracker.tick("user-2", "paper:2", true, 55_000), null);
  assert.equal(tracker.tick("user-2", "paper:2", true, 65_000), 30);
});

// ---- Pagination regressions: a started recommendation feed never restarts as discovery ----

function recommendationItems(requestId: string, from: number, count: number) {
  return Array.from({ length: count }, (_, index) => ({
    ...paper, id: `paper:${from + index}`, title: `Paper ${from + index}`,
    reason: "与你的研究主题相关", sources: ["inferred_topic"],
    request_id: requestId, rank: from + index,
  }));
}

function recommendationPage(requestId: string, offset: number, total: number, size = 12) {
  const end = Math.min(offset + size, total);
  return {
    items: recommendationItems(requestId, offset + 1, end - offset),
    next_cursor: end < total ? `${requestId}:${end}` : null,
    has_more: end < total, request_id: requestId, total, algorithm_version: "content-v1",
  };
}

function failure(status: number, code: number) {
  return new Response(JSON.stringify({ code, message: "failure" }), {
    status, headers: { "Content-Type": "application/json" },
  });
}

/** Fake BFF: recommendation snapshot of `total` items; failures injected per cursor. */
function fakeBackend(total: number, failures: Map<string, Response[]> = new Map()) {
  const requested: Array<{ url: string; expectedUser: string | null }> = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = String(input);
    requested.push({ url, expectedUser: new Headers(init?.headers).get("x-shenzhi-expected-user-id") });
    if (url.includes("/discovery/")) {
      return json({ items: [{ ...paper, id: "global:1" }], next_cursor: "daily-1", has_more: true,
        snapshot_id: "global-snapshot", total: 300 });
    }
    const cursor = new URL(url, "http://local").searchParams.get("cursor") ?? "";
    const injected = failures.get(cursor)?.shift();
    if (injected) return injected;
    const offset = cursor ? Number(cursor.split(":")[1]) : 0;
    return json(recommendationPage("request-1", offset, total));
  };
  return { requested, fetchImpl };
}

test("a failed later recommendation page is thrown, never replaced by discovery", async () => {
  const original = globalThis.fetch;
  const backend = fakeBackend(30, new Map([["request-1:12", [failure(503, 20004)]]]));
  globalThis.fetch = backend.fetchImpl;
  try {
    const first = await fetchHomeFeedPage(null, "user-a");
    assert.equal(first.source, "recommendation");
    await assert.rejects(fetchHomeFeedPage(first.nextCursor, "user-a"));
    assert.equal(backend.requested.some(({ url }) => url.includes("/discovery/")), false);
    // Retrying the same cursor continues exactly where the snapshot left off.
    const second = await fetchHomeFeedPage(first.nextCursor, "user-a");
    assert.deepEqual(second.items.map((item) => item.recommendationRank), Array.from({ length: 12 }, (_, i) => i + 13));
    assert.ok(backend.requested.every(({ expectedUser }) => expectedUser === "user-a"));
  } finally {
    globalThis.fetch = original;
  }
});

test("an expired recommendation snapshot asks for a restart instead of falling back", async () => {
  const original = globalThis.fetch;
  const backend = fakeBackend(30, new Map([["request-1:12", [failure(409, 20001)]]]));
  globalThis.fetch = backend.fetchImpl;
  try {
    const first = await fetchHomeFeedPage(null, "user-a");
    await assert.rejects(fetchHomeFeedPage(first.nextCursor, "user-a"), RecommendationFeedExpiredError);
    assert.equal(backend.requested.some(({ url }) => url.includes("/discovery/")), false);
  } finally {
    globalThis.fetch = original;
  }
});

test("an account-switch precondition failure on a later page is not treated as expiry", async () => {
  const original = globalThis.fetch;
  const backend = fakeBackend(30, new Map([["request-1:12", [failure(409, 10003)]]]));
  globalThis.fetch = backend.fetchImpl;
  try {
    const first = await fetchHomeFeedPage(null, "user-a");
    await assert.rejects(fetchHomeFeedPage(first.nextCursor, "user-a"), (error: unknown) =>
      !(error instanceof RecommendationFeedExpiredError));
    assert.equal(backend.requested.some(({ url }) => url.includes("/discovery/")), false);
  } finally {
    globalThis.fetch = original;
  }
});

test("an empty first recommendation page degrades the whole list to discovery", async () => {
  const original = globalThis.fetch;
  const backend = fakeBackend(0);
  globalThis.fetch = backend.fetchImpl;
  try {
    const first = await fetchHomeFeedPage(null, "user-a");
    assert.equal(first.source, "discovery");
    assert.equal(first.nextCursor, "discovery:daily-1");
    assert.equal(first.items[0].recommendationRequestId, undefined);
  } finally {
    globalThis.fetch = original;
  }
});

function feedObserver(cache: QueryClient, userId: string | null) {
  return new InfiniteQueryObserver<DiscoveryFeedPage, Error, InfiniteData<DiscoveryFeedPage>, readonly unknown[], string | null>(cache, {
    queryKey: ["home-feed", userId],
    queryFn: ({ pageParam }) => fetchHomeFeedPage(pageParam, userId),
    initialPageParam: null,
    getNextPageParam: (page) => page.hasMore ? page.nextCursor ?? undefined : undefined,
    retry: false,
  });
}

function loadedIds(observer: ReturnType<typeof feedObserver>) {
  return observer.getCurrentResult().data?.pages.flatMap((page) => page.items.map((item) => item.id)) ?? [];
}

test("infinite feed keeps loaded pages after a mid-scroll failure and resumes without gaps", async () => {
  const original = globalThis.fetch;
  const backend = fakeBackend(30, new Map([["request-1:12", [failure(503, 20004)]]]));
  globalThis.fetch = backend.fetchImpl;
  const cache = new QueryClient();
  const observer = feedObserver(cache, "user-a");
  const stop = observer.subscribe(() => {});
  try {
    await observer.refetch();
    assert.equal(loadedIds(observer).length, 12);
    const failed = await observer.fetchNextPage();
    assert.equal(failed.isFetchNextPageError, true);
    // The loaded page survives and nothing from discovery was appended.
    assert.equal(loadedIds(observer).length, 12);
    await observer.fetchNextPage();
    await observer.fetchNextPage();
    const ids = loadedIds(observer);
    assert.equal(observer.getCurrentResult().hasNextPage, false);
    assert.equal(ids.length, 30);
    assert.equal(new Set(ids).size, 30);
    assert.deepEqual(ids, Array.from({ length: 30 }, (_, i) => `paper:${i + 1}`));
    assert.equal(backend.requested.some(({ url }) => url.includes("/discovery/")), false);
  } finally {
    stop();
    cache.clear();
    globalThis.fetch = original;
  }
});

test("infinite feed restarts from a new first page only after an explicit reset", async () => {
  const original = globalThis.fetch;
  const backend = fakeBackend(30, new Map([["request-1:12", [failure(409, 20001)]]]));
  globalThis.fetch = backend.fetchImpl;
  const cache = new QueryClient();
  const observer = feedObserver(cache, "user-a");
  const stop = observer.subscribe(() => {});
  try {
    await observer.refetch();
    const failed = await observer.fetchNextPage();
    assert.ok(failed.error instanceof RecommendationFeedExpiredError);
    assert.equal(loadedIds(observer).length, 12);
    await cache.resetQueries({ queryKey: ["home-feed", "user-a"] });
    assert.equal(observer.getCurrentResult().data?.pages.length, 1);
    assert.deepEqual(loadedIds(observer).slice(0, 2), ["paper:1", "paper:2"]);
  } finally {
    stop();
    cache.clear();
    globalThis.fetch = original;
  }
});

test("switching accounts drops the previous user's recommendation pages", async () => {
  const { clearOtherInteractionIdentities } = await import("../../features/knowledge/interactions/cache.js");
  const cache = new QueryClient();
  cache.setQueryData(["home-feed", "user-a"], { pages: [], pageParams: [] });
  cache.setQueryData(["home-feed", null], { pages: [], pageParams: [] });
  clearOtherInteractionIdentities(cache, "user-b");
  assert.equal(cache.getQueryData(["home-feed", "user-a"]), undefined);
  assert.notEqual(cache.getQueryData(["home-feed", null]), undefined);
  clearOtherInteractionIdentities(cache, "");
  assert.notEqual(cache.getQueryData(["home-feed", null]), undefined);
  cache.clear();
});

test("behavior events carry only the expected-user precondition, never an owner field", async () => {
  const original = globalThis.fetch;
  const seen: Array<{ header: string | null; body: Record<string, unknown> }> = [];
  globalThis.fetch = async (_input, init) => {
    seen.push({
      header: new Headers(init?.headers).get("x-shenzhi-expected-user-id"),
      body: JSON.parse(String(init?.body)).events[0],
    });
    return json({ inserted: 1 });
  };
  try {
    recordPaperBehavior({ userId: "user-a", eventType: "paper_click", paperId: "paper:1", source: "discovery" });
    recordPaperBehavior({ userId: "", eventType: "paper_click", paperId: "paper:1", source: "discovery" });
    assert.equal(recordSearchSubmit("RAG", ""), null);
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.equal(seen.length, 1);
    assert.equal(seen[0].header, "user-a");
    assert.equal("user_id" in seen[0].body, false);
  } finally {
    globalThis.fetch = original;
  }
});
