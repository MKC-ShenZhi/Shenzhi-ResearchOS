"use client";

import {
  fetchDiscoveryPapers,
  type DiscoveryPaperDto,
  type DiscoveryPaperPageDto,
} from "../../../clients/backend/discovery";
import type { FeedPaper } from "../../../types";
import { fetchRecommendationPapers } from "../../../clients/backend/recommendations";

export const DISCOVERY_PAGE_SIZE = 12;
const VENUE_TONES: FeedPaper["venueTone"][] = ["violet", "amber", "green"];

function stableVenueTone(id: string): FeedPaper["venueTone"] {
  let hash = 0;
  for (const character of id) hash = (hash + character.charCodeAt(0)) % VENUE_TONES.length;
  return VENUE_TONES[hash];
}

function formatAuthors(authors: string[]): string {
  if (authors.length === 0) return "作者未知";
  const visible = authors.slice(0, 5).join(" · ");
  return authors.length > 5 ? `${visible} 等` : visible;
}

export function mapDiscoveryPaper(item: Omit<DiscoveryPaperDto, "year"> & { year: number | null }): FeedPaper {
  return {
    id: item.id,
    date: item.year === null ? "年份未知" : String(item.year),
    venue: item.venue?.trim() || "预印本",
    venueTone: stableVenueTone(item.id),
    authors: formatAuthors(item.authors),
    title: item.title,
    abstract: item.abstract,
    aiLink: "AI 深度解读",
    tags: [],
    thumbnailUrl: item.thumbnail_url,
  };
}

export interface DiscoveryFeedPage {
  items: FeedPaper[];
  nextCursor: string | null;
  hasMore: boolean;
  snapshotId: string;
  total: number;
}

export async function fetchDiscoveryFeedPage(cursor: string | null): Promise<DiscoveryFeedPage> {
  const response: DiscoveryPaperPageDto = await fetchDiscoveryPapers(cursor, DISCOVERY_PAGE_SIZE);
  return {
    items: response.items.map(mapDiscoveryPaper),
    nextCursor: response.next_cursor,
    hasMore: response.has_more,
    snapshotId: response.snapshot_id,
    total: response.total,
  };
}

export async function fetchHomeFeedPage(cursor: string | null, personalized: boolean): Promise<DiscoveryFeedPage> {
  if (!personalized || cursor?.startsWith("discovery:")) {
    const discoveryCursor = cursor?.startsWith("discovery:") ? cursor.slice("discovery:".length) : null;
    const page = await fetchDiscoveryFeedPage(discoveryCursor);
    return { ...page, nextCursor: page.nextCursor ? `discovery:${page.nextCursor}` : null };
  }
  try {
    const page = await fetchRecommendationPapers(cursor, DISCOVERY_PAGE_SIZE);
    if (!cursor && page.items.length === 0) throw new Error("recommendation pool is empty");
    return {
      items: page.items.map((item) => ({
        ...mapDiscoveryPaper(item),
        recommendationReason: item.reason,
        recommendationRequestId: item.request_id,
        recommendationRank: item.rank,
      })),
      nextCursor: page.next_cursor,
      hasMore: page.has_more,
      snapshotId: page.request_id,
      total: page.total,
    };
  } catch {
    const page = await fetchDiscoveryFeedPage(null);
    return { ...page, nextCursor: page.nextCursor ? `discovery:${page.nextCursor}` : null };
  }
}
