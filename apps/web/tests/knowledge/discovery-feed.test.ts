import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import test from "node:test";

import type { DiscoveryPaperDto } from "../../clients/backend/discovery.js";
import {
  DISCOVERY_PAGE_SIZE,
  mapDiscoveryPaper,
} from "../../features/search/services/discovery-feed.js";

const FEED_LIST_SOURCE = readFileSync("features/search/components/feed-list.tsx", "utf8");
const PAPER_CARD_SOURCE = readFileSync("features/search/components/paper-card.tsx", "utf8");
const HOME_SOURCE = readFileSync("features/home/HomePage.tsx", "utf8");
const BACKEND_CLIENT_SOURCE = readFileSync("clients/backend/discovery.ts", "utf8");

function discoveryPaper(overrides: Partial<DiscoveryPaperDto> = {}): DiscoveryPaperDto {
  return {
    id: "paper:2604.17730v1",
    title: "A real paper title",
    abstract: "A real abstract",
    authors: ["First Author", "Second Author"],
    year: 2026,
    venue: "ACL",
    pdf_url: "https://arxiv.org/pdf/2604.17730v1",
    thumbnail_url: "/paper-thumbnails/2604.17730v1.webp",
    ...overrides,
  };
}

test("discovery mapper preserves display metadata without inventing engagement or tags", () => {
  const mapped = mapDiscoveryPaper(discoveryPaper({
    venue: null,
    authors: ["A One", "B Two", "C Three", "D Four", "E Five", "F Six"],
  }));

  assert.equal(mapped.id, "paper:2604.17730v1");
  assert.equal(mapped.date, "2026");
  assert.equal(mapped.venue, "预印本");
  assert.equal(mapped.authors, "A One · B Two · C Three · D Four · E Five 等");
  assert.deepEqual(mapped.tags, []);
  assert.equal(mapped.thumbnailUrl, "/paper-thumbnails/2604.17730v1.webp");
  assert.equal("likes" in mapped, false);
  assert.equal("citations" in mapped, false);
});

test("home uses one cursor feed with automatic and recoverable pagination", () => {
  assert.equal(DISCOVERY_PAGE_SIZE, 12);
  assert.match(HOME_SOURCE, /论文发现/);
  assert.doesNotMatch(HOME_SOURCE, /FeedTabs|activeTab|推荐|前沿|关注/);
  assert.match(FEED_LIST_SOURCE, /useInfiniteQuery/);
  assert.match(FEED_LIST_SOURCE, /IntersectionObserver/);
  assert.match(FEED_LIST_SOURCE, /rootMargin:\s*"600px 0px"/);
  assert.match(FEED_LIST_SOURCE, /isFetchNextPageError/);
  assert.match(FEED_LIST_SOURCE, /new Map/);
  assert.match(BACKEND_CLIENT_SOURCE, /\/discovery\/papers/);
  assert.match(BACKEND_CLIENT_SOURCE, /query\.set\("cursor", cursor\)/);
});

test("all 300 packaged paper images are real WebP static assets", () => {
  const snapshot = JSON.parse(
    readFileSync("../backend/app/data/home_discovery_snapshot.json", "utf8"),
  ) as { items: Array<{ thumbnail_url: string }> };
  const assets = readdirSync("public/paper-thumbnails").filter((name) => name.endsWith(".webp"));

  assert.equal(snapshot.items.length, 300);
  assert.equal(assets.length, 300);
  for (const item of snapshot.items) {
    const path = `public${item.thumbnail_url}`;
    assert.equal(existsSync(path), true, path);
    const header = readFileSync(path).subarray(0, 12);
    assert.equal(header.subarray(0, 4).toString("ascii"), "RIFF");
    assert.equal(header.subarray(8, 12).toString("ascii"), "WEBP");
  }
});

test("paper cards keep the existing detail navigation and load thumbnails on mobile", () => {
  assert.match(
    PAPER_CARD_SOURCE,
    /const detailHref = paperHref\(paper\.id, \{ mode: "create", source: returnTo \}\)/,
  );
  assert.equal(PAPER_CARD_SOURCE.match(/href=\{detailHref\}/g)?.length, 3);
  assert.doesNotMatch(PAPER_CARD_SOURCE, /hidden w-full max-w-\[320px\]/);
});
