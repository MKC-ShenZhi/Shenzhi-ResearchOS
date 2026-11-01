"use client";

import {
  fetchDiscoveryPapers,
  type DiscoveryPaperDto,
  type DiscoveryPaperPageDto,
} from "../../../clients/backend/discovery";
import type { FeedPaper } from "../../../types";
import { ApiError } from "../../../clients/backend/http";
import { getPaperThumbnailUrl } from "../../../lib/paper-thumbnail";
import {
  formatPaperAuthors,
  formatPaperYear,
  paperVenueTone,
  pickPaperTopics,
} from "../../knowledge/papers/paper-card-model";
import { fetchRecommendationPapers } from "../../../clients/backend/recommendations";

export const DISCOVERY_PAGE_SIZE = 12;

export function mapDiscoveryPaper(item: Omit<DiscoveryPaperDto, "year"> & { year: number | null }): FeedPaper {
  return {
    id: item.id,
    date: formatPaperYear(item.year),
    venue: item.venue?.trim() || "预印本",
    venueTone: paperVenueTone(item.id),
    authors: formatPaperAuthors(item.authors),
    title: item.title,
    abstract: item.abstract,
    tags: pickPaperTopics(item.keywords, item.subjects),
    // Curated papers keep their static thumbnail; pool and recalled papers use the knowledge image.
    thumbnailUrl: item.thumbnail_url ?? getPaperThumbnailUrl(item.image_id),
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
