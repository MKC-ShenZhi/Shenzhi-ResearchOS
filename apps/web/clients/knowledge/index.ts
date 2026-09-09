"use client";

import type { KnowledgeClient } from "./client";
import { BffKnowledgeClient } from "./bff";
import { MockKnowledgeClient } from "./mock";

export { KnowledgeClientError } from "./client";
export type { KnowledgeClient } from "./client";
export { MockKnowledgeClient } from "./mock";
export type { MockKnowledgeClientOptions, MockScenario } from "./mock";
export { BffKnowledgeClient } from "./bff";

export type {
  KnowledgeSearchParams,
  KnowledgePaperHit,
  KnowledgePaperDetail,
  ReadingHistoryItem,
  ReadingHistoryResponse,
  CollectionPaperItem,
  CollectionPaperListResponse,
  KnowledgeGraph,
  KnowledgeGraphDepth,
  KnowledgeGraphNode,
  KnowledgeGraphNodeProperties,
  KnowledgeGraphEdge,
  KnowledgeGraphRelation,
  KnowledgeNodeKind,
  KnowledgeRelatedPaper,
  KnowledgeRelationDirection,
  KnowledgeErrorCode,
  KnowledgeApiError,
} from "./types";
export { KNOWLEDGE_RELATION_LABELS } from "./types";

/**
 * 知识底座 Client 工厂。
 *
 * 默认使用 BffKnowledgeClient（走同源 Next.js BFF → ShenZhi FastAPI）。
 * 只有显式设置
 *   NEXT_PUBLIC_KNOWLEDGE_SOURCE=mock
 * 才启用 MockKnowledgeClient，供开发、测试或 demo fixture 使用。
 */
export function getKnowledgeClient(): KnowledgeClient {
  const source =
    typeof process !== "undefined" && typeof process.env !== "undefined"
      ? process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE
      : undefined;

  if (source === "mock") return new MockKnowledgeClient();
  return new BffKnowledgeClient();
}
