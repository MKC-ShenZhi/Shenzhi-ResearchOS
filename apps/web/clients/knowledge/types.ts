/**
 * 知识底座（论文检索 / 详情 / 关系图谱）前端契约类型。
 *
 * 契约来源：知识底座科研组 Contract（同学调研确认）。
 * 稳定依赖字段：
 *   Search   → id / title / abstract / authors / year / venue / keywords / subjects / score / rank
 *   Detail   → 同上 + doi / pdfUrl / citationCount / referenceCount
 *   Graph    → rootId / nodes[{id,kind,label,properties}] / edges[{sourceId,targetId,relation,description,weight}]
 *
 * 约定：
 * - id 一律作为 opaque string 使用，禁止解析内部格式
 * - year / citationCount 等为 null 表示上游未提供，不等于 0，UI 不得显示为 0
 * - kind / relation 是开放字符串，未知类型必须有默认展示
 */

/** 论文搜索请求参数 */
export interface KnowledgeSearchParams {
  query: string;
  topK: number;

  yearFrom: number | null;
  yearTo: number | null;

  venue: string[];
  author: string[];
  keyword: string[];
  subject: string[];
}

/** 搜索结果单条（论文） */
export interface KnowledgePaperHit {
  id: string;
  title: string;
  abstract: string | null;
  authors: string[];
  year: number | null;
  venue: string | null;
  keywords: string[];
  subjects: string[];
  /** 相关性得分（非百分比） */
  score: number | null;
  rank: number | null;
  provenance: unknown;
}

/** 论文详情 */
export interface KnowledgePaperDetail {
  id: string;
  title: string;
  abstract: string | null;
  authors: string[];
  year: number | null;
  venue: string | null;

  doi: string | null;
  pdfUrl: string | null;

  keywords: string[];
  subjects: string[];

  /** null = 上游未提供，禁止显示为 0 */
  citationCount: number | null;
  referenceCount: number | null;

  provenance: unknown;
}

export interface ReadingHistoryItem extends KnowledgePaperDetail {
  paper_id: string;
  last_viewed_at: string;
}

export interface ReadingHistoryResponse {
  items: ReadingHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CollectionPaperItem extends KnowledgePaperDetail {
  paper_id: string;
  added_at: string;
}

export interface CollectionPaperListResponse {
  items: CollectionPaperItem[];
  total: number;
  page: number;
  page_size: number;
}

/** 图谱节点 kind 是开放字符串；这里只列出当前已知类型，未知类型默认展示 */
export type KnowledgeNodeKind =
  | "Paper"
  | "Author"
  | "Method"
  | "Topic"
  | "Conference"
  | "Funding"
  | "Institution"
  | "Venue"
  | (string & {});

export interface KnowledgeGraphNodeProperties {
  year?: number | null;
  venue?: string | null;
  abstract?: string | null;
  authors?: string[];
  doi?: string | null;
  pdfUrl?: string | null;
  external?: boolean | null;
  /** 其余开放属性 */
  [key: string]: unknown;
}

export interface KnowledgeGraphNode {
  id: string;
  kind: KnowledgeNodeKind;
  label: string;
  properties: KnowledgeGraphNodeProperties;
  provenance: unknown;
}

/** relation 是开放字符串；CITES 语义统一为 sourceId 引用了 targetId */
export type KnowledgeGraphRelation =
  | "CITES"
  | "AUTHORED_BY"
  | "PROPOSES"
  | "USES_AS_BASELINE"
  | "HAS_TOPIC"
  | "PUBLISHED_IN"
  | "FUNDED_BY"
  | "AFFILIATED_WITH"
  | "PART_OF"
  | (string & {});

export interface KnowledgeGraphEdge {
  sourceId: string;
  targetId: string;
  relation: KnowledgeGraphRelation;
  description: string | null;
  weight: number | null;
  provenance: unknown;
}

export interface KnowledgeGraph {
  rootId: string;
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  /** Backend provenance is retained for downstream diagnostics and attribution. */
  provenance?: unknown;
}

/** Backend-supported graph depth. */
export type KnowledgeGraphDepth = 1 | 2;

/** 错误码（契约统一） */
export type KnowledgeErrorCode =
  | "INVALID_ARGUMENT"
  | "NOT_FOUND"
  | "RATE_LIMITED"
  | "UPSTREAM_UNAVAILABLE"
  | "TIMEOUT"
  | "CONTRACT_VIOLATION"
  | "UNKNOWN";

/** 统一错误对象 */
export interface KnowledgeApiError {
  code: KnowledgeErrorCode;
  message: string;
  retryable: boolean;
  requestId: string | null;
}

/** 关联论文方向（依据 CITES 语义推导） */
export type KnowledgeRelationDirection = "reference" | "citation" | "both";

/** 图谱中的关联论文（左栏列表用） */
export interface KnowledgeRelatedPaper {
  id: string;
  title: string;
  year: number | null;
  venue: string | null;
  authors: string[];
  citationCount: number | null;
  relationDirection: KnowledgeRelationDirection;
}

/** 当前已知图谱关系展示元信息 */
export const KNOWLEDGE_RELATION_LABELS: Record<string, string> = {
  CITES: "引用",
  AUTHORED_BY: "作者",
  PROPOSES: "提出",
  USES_AS_BASELINE: "基线对比",
  HAS_TOPIC: "主题",
  PUBLISHED_IN: "发表于",
  FUNDED_BY: "资助",
  AFFILIATED_WITH: "所属机构",
  PART_OF: "属于",
};
