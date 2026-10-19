import type { KnowledgePaperDetail } from "@/clients/knowledge/types";

/** V2 已对齐字段；null / 缺省表示未提供，不能被解释为 0。 */
export interface ScholarProfile {
  scholar_id: string;
  name_zh?: string | null;
  name_en?: string | null;
  avatar_path?: string | null;
  affiliations?: Array<{
    institution?: string | null;
    position?: string | null;
  }> | null;
  bio_zh?: string | null;
  bio_en?: string | null;
  metrics?: {
    paper_count?: number | null;
    citation_count?: number | null;
  } | null;
  annual_citations?: Array<{ year: number; count: number | null }> | null;
  updated_at?: string | null;
}

export interface ScholarProfileDetail {
  scholar: ScholarProfile;
  /** 复用论文库契约；与 scholar_id 的演示关联由数据源维护。 */
  papers: KnowledgePaperDetail[];
}

/** 仅学者 V2 使用；未来 Adapter 经 ShenZhi API 接入，旧 KnowledgeClient 不变。 */
export interface ScholarProvider {
  cacheKey: string;
  search(query: string, signal?: AbortSignal): Promise<ScholarProfile[]>;
  detail(
    id: string,
    signal?: AbortSignal,
  ): Promise<ScholarProfileDetail | null>;
}
