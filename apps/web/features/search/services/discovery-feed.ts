"use client";

import {
  fetchDiscoveryPapers,
  type DiscoveryPaperDto,
  type DiscoveryPaperPageDto,
} from "../../../clients/backend/discovery";
import type { FeedPaper } from "../../../types";

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

export function mapDiscoveryPaper(item: DiscoveryPaperDto): FeedPaper {
  return {
    id: item.id,
    date: String(item.year),
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
