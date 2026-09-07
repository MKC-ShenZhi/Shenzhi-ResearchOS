"use client";

import { apiJson, ApiError } from "../backend/http";
import { KnowledgeClientError, type KnowledgeClient } from "./client";
import type {
  KnowledgeErrorCode,
  KnowledgeGraph,
  KnowledgeGraphDepth,
  KnowledgePaperDetail,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
} from "./types";

/**
 * 知识底座 BFF Client：经 ShenZhi FastAPI 访问知识底座科研组能力。
 *
 * 页面无感知：请求统一走同源 /api/v1（Next.js BFF 转发），不在浏览器
 * 暴露 FastAPI 或外部知识库地址。
 */

const KNOWLEDGE_ERROR_CODES = new Set<KnowledgeErrorCode>([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "RATE_LIMITED",
  "UPSTREAM_UNAVAILABLE",
  "TIMEOUT",
  "CONTRACT_VIOLATION",
  "UNKNOWN",
]);

function toKnowledgeError(error: unknown): KnowledgeClientError {
  if (error instanceof KnowledgeClientError) return error;
  if (error instanceof ApiError) {
    if (typeof error.code === "string") {
      const code = KNOWLEDGE_ERROR_CODES.has(error.code as KnowledgeErrorCode)
        ? error.code as KnowledgeErrorCode
        : "UNKNOWN";
      return new KnowledgeClientError(code, error.message, {
        retryable: error.retryable ?? false,
        requestId: error.requestId,
      });
    }

    const infrastructureCode = error.status === 504
      ? "TIMEOUT"
      : error.status >= 500
        ? "UPSTREAM_UNAVAILABLE"
        : "UNKNOWN";
    return new KnowledgeClientError(infrastructureCode, "知识底座服务异常", {
      retryable: error.retryable ?? error.status >= 500,
      requestId: error.requestId,
    });
  }

  if (error instanceof Error && (error.name === "AbortError" || error.name === "TimeoutError")) {
    return new KnowledgeClientError("TIMEOUT", "知识底座服务响应超时", {
      retryable: true,
    });
  }

  return new KnowledgeClientError(
    "UNKNOWN",
    "知识底座服务异常",
  );
}

export class BffKnowledgeClient implements KnowledgeClient {
  async search(params: KnowledgeSearchParams): Promise<KnowledgeSearchResponse> {
    try {
      return await apiJson<KnowledgeSearchResponse>("/knowledge/search", {
        method: "POST",
        body: JSON.stringify({
          query: params.query,
          topK: params.topK,
          offset: params.offset,
          yearFrom: params.yearFrom,
          yearTo: params.yearTo,
          venue: params.venue,
          author: params.author,
          keyword: params.keyword,
          subject: params.subject,
        }),
      });
    } catch (error) {
      throw toKnowledgeError(error);
    }
  }

  async paper(paperId: string): Promise<KnowledgePaperDetail> {
    try {
      return await apiJson<KnowledgePaperDetail>(
        `/knowledge/paper?paperId=${encodeURIComponent(paperId)}`,
      );
    } catch (error) {
      throw toKnowledgeError(error);
    }
  }

  async graph(paperId: string, depth: KnowledgeGraphDepth = 1): Promise<KnowledgeGraph> {
    try {
      return await apiJson<KnowledgeGraph>(
        `/knowledge/graph?paperId=${encodeURIComponent(paperId)}&depth=${depth}`,
      );
    } catch (error) {
      throw toKnowledgeError(error);
    }
  }
}
