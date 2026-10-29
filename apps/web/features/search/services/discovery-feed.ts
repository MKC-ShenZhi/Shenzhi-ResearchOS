"use client";

import {
  fetchDiscoveryPapers,
  type DiscoveryPaperDto,
  type DiscoveryPaperPageDto,
} from "../../../clients/backend/discovery";
import type { FeedPaper } from "../../../types";
import { ApiError } from "../../../clients/backend/http";
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
  /** Which feed produced this page; a recommendation feed never continues as discovery. */
  source?: "recommendation" | "discovery";
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

const DISCOVERY_CURSOR_PREFIX = "discovery:";

/** The recommendation snapshot behind a cursor is gone; only a restart from page one can recover. */
export class RecommendationFeedExpiredError extends Error {
  constructor() {
    super("推荐列表已过期，请刷新后重新浏览");
    this.name = "RecommendationFeedExpiredError";
  }
}

async function homeDiscoveryPage(cursor: string | null): Promise<DiscoveryFeedPage> {
  const page = await fetchDiscoveryFeedPage(cursor);
  return {
    ...page,
    nextCursor: page.nextCursor ? `${DISCOVERY_CURSOR_PREFIX}${page.nextCursor}` : null,
    source: "discovery",
  };
}

async function recommendationPage(cursor: string | null, userId: string): Promise<DiscoveryFeedPage> {
  const page = await fetchRecommendationPapers(cursor, userId, DISCOVERY_PAGE_SIZE);
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
    source: "recommendation",
  };
}

/**
 * 首页 Feed：登录用户走推荐，匿名用户沿用全局发现。
 *
 * 只有第一页可以降级为全局发现：此时列表尚未开始，整份列表都来自发现 Feed，
 * 后续游标带 `discovery:` 前缀继续发现分页。推荐分页一旦开始，后续页失败必须
 * 抛出，由 useInfiniteQuery 保留已加载页面并重试同一游标；绝不能把发现第一页
 * 当作推荐下一页返回，否则会重复、跳页或让列表重新开始。
 */
export async function fetchHomeFeedPage(cursor: string | null, userId: string | null): Promise<DiscoveryFeedPage> {
  if (!userId || cursor?.startsWith(DISCOVERY_CURSOR_PREFIX)) {
    return homeDiscoveryPage(cursor?.startsWith(DISCOVERY_CURSOR_PREFIX)
      ? cursor.slice(DISCOVERY_CURSOR_PREFIX.length)
      : null);
  }
  if (cursor === null) {
    try {
      const page = await recommendationPage(null, userId);
      if (page.items.length > 0) return page;
    } catch {
      // Fall through: an unavailable or empty first recommendation page keeps discovery usable.
    }
    return homeDiscoveryPage(null);
  }
  try {
    return await recommendationPage(cursor, userId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 409 && error.code === 20001) {
      throw new RecommendationFeedExpiredError();
    }
    throw error;
  }
}
