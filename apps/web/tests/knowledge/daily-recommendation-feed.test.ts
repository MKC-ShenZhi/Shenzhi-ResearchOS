import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { KnowledgePaperHit } from "../../clients/knowledge/types.js";
import {
  mapRecommendationToFeedPaper,
  readCachedRecommendationFeed,
  recommendationDate,
  recommendationStorageKey,
  writeCachedRecommendationFeed,
} from "../../features/search/services/daily-recommendation-feed.js";

const FEED_LIST_SOURCE = readFileSync("features/search/components/feed-list.tsx", "utf8");
const PAPER_CARD_SOURCE = readFileSync("features/search/components/paper-card.tsx", "utf8");
const DAILY_SERVICE_SOURCE = readFileSync(
  "features/search/services/daily-recommendation-feed.ts",
  "utf8",
);
const BACKEND_CLIENT_SOURCE = readFileSync("clients/backend/recommendations.ts", "utf8");

function knowledgeHit(index: number, overrides: Partial<KnowledgePaperHit> = {}): KnowledgePaperHit {
  return {
    id: `opaque:paper/${index}`,
    title: `Paper ${index}`,
    abstract: `Abstract ${index}`,
    authors: [`Author ${index}`],
    year: 2025,
    venue: "Venue",
    keywords: ["keyword", "second", "third", "ignored"],
    subjects: ["subject"],
    score: 1,
    rank: index,
    provenance: null,
    ...overrides,
  };
}

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
  };
}

test("daily recommendation mapper preserves real fields without inventing metrics", () => {
  const paper = mapRecommendationToFeedPaper(knowledgeHit(1, {
    id: "paper:opaque/value?part=1",
    abstract: null,
    authors: [],
    year: null,
    venue: null,
    keywords: [],
    subjects: ["subject", "second", "third", "ignored"],
  }));

  assert.equal(paper.id, "paper:opaque/value?part=1");
  assert.equal(paper.date, "年份未知");
  assert.equal(paper.venue, "来源未知");
  assert.equal(paper.authors, "作者未知");
  assert.equal(paper.abstract, "暂无摘要");
  assert.deepEqual(paper.tags, ["subject", "second", "third"]);
  assert.equal("likes" in paper, false);
  assert.equal("citations" in paper, false);
});

test("cache is isolated by identity, tab, and UTC date", () => {
  const storage = memoryStorage();
  const date = recommendationDate(new Date("2026-09-30T23:59:59Z"));
  const items = [mapRecommendationToFeedPaper(knowledgeHit(1))];

  writeCachedRecommendationFeed("user:user-a", "recommend", date, items, storage);

  assert.equal(date, "2026-09-30");
  assert.deepEqual(
    readCachedRecommendationFeed("user:user-a", "recommend", date, storage),
    items,
  );
  assert.equal(
    readCachedRecommendationFeed("user:user-b", "recommend", date, storage),
    undefined,
  );
  assert.equal(
    readCachedRecommendationFeed("user:user-a", "frontier", date, storage),
    undefined,
  );
  assert.match(
    recommendationStorageKey("user:user-a", "recommend", date),
    /^shenzhi:recommendations:user:user-a:recommend:2026-09-30$/,
  );
});

test("cache ignores stale dates and malformed localStorage values", () => {
  const storage = memoryStorage();
  const key = recommendationStorageKey("anonymous", "recommend", "2026-09-30");
  storage.setItem(key, JSON.stringify({ date: "2026-09-29", items: [] }));
  assert.equal(
    readCachedRecommendationFeed("anonymous", "recommend", "2026-09-30", storage),
    undefined,
  );

  storage.setItem(key, "not-json");
  assert.equal(
    readCachedRecommendationFeed("anonymous", "recommend", "2026-09-30", storage),
    undefined,
  );
});

test("feed renders local data first and always revalidates through ShenZhi backend", () => {
  assert.match(FEED_LIST_SOURCE, /initialData:/);
  assert.match(FEED_LIST_SOURCE, /readCachedRecommendationFeed/);
  assert.match(FEED_LIST_SOURCE, /refetchOnMount:\s*"always"/);
  assert.match(FEED_LIST_SOURCE, /staleTime:\s*0/);
  assert.match(BACKEND_CLIENT_SOURCE, /\/discovery\/recommendations/);
  assert.doesNotMatch(DAILY_SERVICE_SOURCE, /getKnowledgeClient|\.search\(/);
});

test("cached data remains visible if background revalidation fails", () => {
  assert.match(FEED_LIST_SOURCE, /isError\s*&&\s*!data/);
});

test("all paper card entries continue using the same opaque paper id", () => {
  assert.equal(
    PAPER_CARD_SOURCE.match(/paperHref\(paper\.id, \{ mode: "create", source: returnTo \}\)/g)?.length,
    3,
  );
});
