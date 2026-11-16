import { apiJson, ApiError } from "./http";
import type { PaperTopic } from "../knowledge/types";

export interface DiscoveryPaperDto {
  id: string;
  title: string;
  abstract: string;
  authors: string[];
  year: number;
  venue: string | null;
  pdf_url: string | null;
  thumbnail_url: string | null;
  /** Knowledge image; packaged fallback papers carry a static `thumbnail_url` instead. */
  image_id?: string | null;
  keywords?: string[];
  subjects?: string[];
  topics?: PaperTopic[];
  /** Home-feed source that placed the paper: daily / trending / personal / fallback. */
  source?: string | null;
}

export interface DiscoveryPaperPageDto {
  items: DiscoveryPaperDto[];
  next_cursor: string | null;
  has_more: boolean;
  /** The composed list the cursors belong to. */
  list_id: string;
  total: number;
}

export async function fetchDiscoveryPapers(
  cursor: string | null,
  limit = 12,
): Promise<DiscoveryPaperPageDto> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return apiJson<DiscoveryPaperPageDto>(`/discovery/papers?${query.toString()}`);
}

export function discoveryQueryRetry(failureCount: number, error: unknown): boolean {
  return failureCount < 1 && error instanceof ApiError && error.status >= 500;
}
