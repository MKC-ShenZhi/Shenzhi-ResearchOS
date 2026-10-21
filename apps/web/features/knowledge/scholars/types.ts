import type { KnowledgePaperDetail } from "@/clients/knowledge/types";
import type { ScholarProfile, ScholarProfilePage, ScholarPapersPage } from "@/clients/knowledge/scholar-profiles";
export type { ScholarProfile } from "@/clients/knowledge/scholar-profiles";

export interface ScholarProfileDetail {
  scholar: ScholarProfile;
  /** Mock fixture relationships; real publications load independently. */
  papers: KnowledgePaperDetail[];
}
export interface ScholarProvider {
  cacheKey: string;
  isDemo: boolean;
  supportsBrowse: boolean;
  search(query: string, signal?: AbortSignal, page?: { limit: number; offset: number }): Promise<ScholarProfilePage>;
  detail(id: string, signal?: AbortSignal): Promise<ScholarProfileDetail | null>;
  papers(id: string, limit: number, offset: number, signal?: AbortSignal): Promise<ScholarPapersPage>;
}
