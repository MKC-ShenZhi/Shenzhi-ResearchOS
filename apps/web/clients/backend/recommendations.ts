import { apiJson, expectedUserHeaders } from "./http";
import type { DiscoveryPaperDto } from "./discovery";

export interface RecommendationPaperDto extends Omit<DiscoveryPaperDto, "year"> {
  year: number | null;
  reason: string;
  sources: string[];
  request_id: string;
  rank: number;
}

export interface RecommendationPageDto {
  items: RecommendationPaperDto[];
  next_cursor: string | null;
  has_more: boolean;
  request_id: string;
  total: number;
  algorithm_version: string;
}

/** `userId` is a stale-tab precondition only; the BFF session still decides the owner. */
export async function fetchRecommendationPapers(cursor: string | null, userId: string, limit = 12) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return apiJson<RecommendationPageDto>(`/recommendations/papers?${query.toString()}`, {
    headers: expectedUserHeaders(userId),
  });
}
