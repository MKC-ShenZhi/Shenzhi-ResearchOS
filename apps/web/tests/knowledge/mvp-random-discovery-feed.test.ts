import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { KnowledgePaperHit, KnowledgeSearchParams } from "../../clients/knowledge/index.js";
import {
  fetchMvpRandomDiscoveryFeed,
  mapKnowledgePaperHitToFeedPaper,
  MVP_RANDOM_DISCOVERY_SEEDS,
} from "../../features/search/services/mvp-random-discovery-feed.js";

const FEED_LIST_SOURCE = readFileSync("features/search/components/feed-list.tsx", "utf8");
const PAPER_CARD_SOURCE = readFileSync("features/search/components/paper-card.tsx", "utf8");
const MVP_SERVICE_SOURCE = readFileSync(
  "features/search/services/mvp-random-discovery-feed.ts",
  "utf8",
);

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

test("discovery mapper preserves opaque ids and never invents engagement metrics", () => {
  const paper = mapKnowledgePaperHitToFeedPaper(knowledgeHit(1, {
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

test("frontier discovery performs one broad search, filters recent years and returns real ids", async () => {
  const calls: KnowledgeSearchParams[] = [];
  const hits = Array.from({ length: 12 }, (_, index) => knowledgeHit(index));
  const papers = await fetchMvpRandomDiscoveryFeed("frontier", {
    client: {
      async search(params) {
        calls.push(params);
        return { results: hits };
      },
    },
    random: () => 0,
    currentYear: 2026,
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].query, MVP_RANDOM_DISCOVERY_SEEDS[0]);
  assert.equal(calls[0].topK, 20);
  assert.equal(calls[0].yearFrom, 2025);
  assert.equal(calls[0].yearTo, null);
  assert.equal(papers.length, 8);
  assert.ok(papers.every((paper) => hits.some((hit) => hit.id === paper.id)));
});

test("non-frontier tabs use the random fallback without a year filter", async () => {
  for (const tab of ["recommend", "follow", "research"] as const) {
    let params: KnowledgeSearchParams | undefined;
    await fetchMvpRandomDiscoveryFeed(tab, {
      client: {
        async search(searchParams) {
          params = searchParams;
          return { results: [] };
        },
      },
      random: () => 0.999,
      currentYear: 2026,
    });

    assert.equal(params?.query, MVP_RANDOM_DISCOVERY_SEEDS.at(-1));
    assert.equal(params?.yearFrom, null);
  }
});

test("knowledge search errors propagate instead of falling back to mock papers", async () => {
  await assert.rejects(
    fetchMvpRandomDiscoveryFeed("recommend", {
      client: {
        async search() {
          throw new Error("knowledge unavailable");
        },
      },
      random: () => 0,
    }),
    /knowledge unavailable/,
  );
});

test("discovery UI caches by tab and never uses mock feed placeholders", () => {
  assert.match(FEED_LIST_SOURCE, /queryKey:\s*\["discovery-feed", tab\]/);
  assert.match(FEED_LIST_SOURCE, /staleTime:\s*5 \* 60_000/);
  assert.doesNotMatch(FEED_LIST_SOURCE, /feedPapers|placeholderData/);
});

test("all paper card detail entries build a route from the same opaque real id", () => {
  assert.equal(PAPER_CARD_SOURCE.match(/paperHref\(paper\.id, \{ mode: "create", source: returnTo \}\)/g)?.length, 3);
});

test("the temporary service is removable and never performs per-paper detail requests", () => {
  assert.match(MVP_SERVICE_SOURCE, /TODO\(MVP-RANDOM-DISCOVERY-FEED\)/);
  assert.doesNotMatch(MVP_SERVICE_SOURCE, /\.paper\(/);
});
