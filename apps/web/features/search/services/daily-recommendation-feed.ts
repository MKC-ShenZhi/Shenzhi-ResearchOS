"use client";

import {
  fetchDailyRecommendations,
  type DiscoveryFeedTab,
} from "../../../clients/backend/recommendations";
import type { KnowledgePaperHit } from "../../../clients/knowledge/types";
import { getPaperThumbnailUrl } from "../../../lib/paper-thumbnail";
import type { FeedPaper } from "../../../types";

export type { DiscoveryFeedTab };

const FEED_SIZE = 8;
const STORAGE_PREFIX = "shenzhi:recommendations";
const VENUE_TONES: FeedPaper["venueTone"][] = ["violet", "amber", "green"];

interface CachedRecommendationFeed {
  date: string;
  items: FeedPaper[];
}

function stableVenueTone(id: string): FeedPaper["venueTone"] {
  let hash = 0;
  for (const character of id) hash = (hash + character.charCodeAt(0)) % VENUE_TONES.length;
  return VENUE_TONES[hash];
}

function discoveryTags(hit: KnowledgePaperHit): string[] {
  const source = hit.keywords.length > 0 ? hit.keywords : hit.subjects;
  return [...new Set(source.map((tag) => tag.trim()).filter(Boolean))].slice(0, 3);
}

/** Maps only fields stored in the daily pool; no engagement metrics are invented. */
export function mapRecommendationToFeedPaper(hit: KnowledgePaperHit): FeedPaper {
  return {
    id: hit.id,
    date: hit.year === null ? "年份未知" : String(hit.year),
    venue: hit.venue?.trim() || "来源未知",
    venueTone: stableVenueTone(hit.id),
    authors: hit.authors.length > 0 ? hit.authors.join(" · ") : "作者未知",
    title: hit.title,
    abstract: hit.abstract?.trim() || "暂无摘要",
    aiLink: "AI 深度解读",
    tags: discoveryTags(hit),
    thumbnailUrl: getPaperThumbnailUrl(hit.id),
  };
}

/** Backend and browser use the same UTC day boundary for recommendation keys. */
export function recommendationDate(date = new Date()): string {
  return date.toISOString().slice(0, 10);
}

export function recommendationStorageKey(
  identityKey: string,
  tab: DiscoveryFeedTab,
  date: string,
): string {
  return `${STORAGE_PREFIX}:${identityKey}:${tab}:${date}`;
}

function isFeedPaper(value: unknown): value is FeedPaper {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<FeedPaper>;
  return typeof item.id === "string" &&
    typeof item.date === "string" &&
    typeof item.venue === "string" &&
    (item.venueTone === "violet" || item.venueTone === "amber" || item.venueTone === "green") &&
    typeof item.authors === "string" &&
    typeof item.title === "string" &&
    typeof item.abstract === "string" &&
    typeof item.aiLink === "string" &&
    Array.isArray(item.tags) && item.tags.every((tag) => typeof tag === "string") &&
    (item.thumbnailUrl === undefined || item.thumbnailUrl === null || typeof item.thumbnailUrl === "string");
}

export function readCachedRecommendationFeed(
  identityKey: string,
  tab: DiscoveryFeedTab,
  date: string,
  storage: Pick<Storage, "getItem"> | null = typeof window === "undefined" ? null : window.localStorage,
): FeedPaper[] | undefined {
  if (!storage) return undefined;
  try {
    const raw = storage.getItem(recommendationStorageKey(identityKey, tab, date));
    if (!raw) return undefined;
    const cached = JSON.parse(raw) as Partial<CachedRecommendationFeed>;
    if (cached.date !== date || !Array.isArray(cached.items) || !cached.items.every(isFeedPaper)) {
      return undefined;
    }
    return cached.items;
  } catch {
    return undefined;
  }
}

export function writeCachedRecommendationFeed(
  identityKey: string,
  tab: DiscoveryFeedTab,
  date: string,
  items: FeedPaper[],
  storage: Pick<Storage, "setItem"> | null = typeof window === "undefined" ? null : window.localStorage,
): void {
  if (!storage) return;
  try {
    storage.setItem(
      recommendationStorageKey(identityKey, tab, date),
      JSON.stringify({ date, items } satisfies CachedRecommendationFeed),
    );
  } catch {
    // Storage can be unavailable or full; the network response remains usable.
  }
}

export async function fetchDailyRecommendationFeed(
  tab: DiscoveryFeedTab,
  identityKey: string,
): Promise<FeedPaper[]> {
  const response = await fetchDailyRecommendations(tab, FEED_SIZE);
  const items = response.items.map(mapRecommendationToFeedPaper);
  writeCachedRecommendationFeed(identityKey, tab, response.date, items);
  return items;
}
