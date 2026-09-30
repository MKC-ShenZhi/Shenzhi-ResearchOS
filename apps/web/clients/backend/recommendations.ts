import type { KnowledgePaperHit } from "../knowledge/types";
import { apiJson, ApiError } from "./http";

export type DiscoveryFeedTab = "recommend" | "frontier" | "follow" | "research";

export interface DailyRecommendationResponse {
  date: string;
  items: KnowledgePaperHit[];
}

export async function fetchDailyRecommendations(
  tab: DiscoveryFeedTab,
  limit = 8,
): Promise<DailyRecommendationResponse> {
  const query = new URLSearchParams({ tab, limit: String(limit) });
  return apiJson<DailyRecommendationResponse>(
    `/discovery/recommendations?${query.toString()}`,
  );
}

export function recommendationQueryRetry(failureCount: number, error: unknown): boolean {
  return failureCount < 1 && error instanceof ApiError && error.status >= 500;
}
