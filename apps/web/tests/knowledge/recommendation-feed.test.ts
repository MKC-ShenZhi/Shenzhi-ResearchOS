import assert from "node:assert/strict";
import test from "node:test";

import { fetchHomeFeedPage } from "../../features/search/services/discovery-feed.js";
import { recordPaperBehavior, recordSearchSubmit } from "../../clients/backend/behavior.js";

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
    const page = await fetchHomeFeedPage(null, true);
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
    const first = await fetchHomeFeedPage(null, true);
    assert.equal(first.items[0].id, "paper:1");
    assert.equal(first.nextCursor, "discovery:daily-1");
    await fetchHomeFeedPage(first.nextCursor, true);
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
    const page = await fetchHomeFeedPage(null, false);
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
    const queryId = recordSearchSubmit("RAG");
    assert.ok(queryId);
    recordPaperBehavior({
      eventType: "search_result_click", paperId: "paper:1", source: "search",
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
      eventType: "abstract_expand", paperId: "paper:1", source: "search",
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
