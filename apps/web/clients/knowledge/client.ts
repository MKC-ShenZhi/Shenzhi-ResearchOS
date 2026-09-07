"use client";

import type {
  KnowledgeApiError,
  KnowledgeErrorCode,
  KnowledgeGraphDepth,
  KnowledgeGraph,
  KnowledgePaperDetail,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
} from "./types";

/**
 * 知识底座前端 Client 统一接口。
 *
 * 页面只依赖本接口；正式运行由 BffKnowledgeClient 实现（bff.ts，
 * 走同源 Next.js BFF → ShenZhi FastAPI），MockKnowledgeClient 仅通过
 * 显式配置用于开发、测试或 demo fixture。
 */
export interface KnowledgeClient {
  /** 论文搜索；无匹配返回空 results（不是错误） */
  search(params: KnowledgeSearchParams): Promise<KnowledgeSearchResponse>;
  /** 论文详情；id 作为 opaque string 使用 */
  paper(paperId: string): Promise<KnowledgePaperDetail>;
  /** 论文关系图谱；默认 depth=1 */
  graph(paperId: string, depth?: KnowledgeGraphDepth): Promise<KnowledgeGraph>;
}

/** 知识底座错误（契约统一格式） */
export class KnowledgeClientError extends Error implements KnowledgeApiError {
  code: KnowledgeErrorCode;
  retryable: boolean;
  requestId: string | null;

  constructor(
    code: KnowledgeErrorCode,
    message: string,
    options: { retryable?: boolean; requestId?: string | null } = {},
  ) {
    super(message);
    this.name = "KnowledgeClientError";
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.requestId = options.requestId ?? null;
  }

  static notFound(message = "未找到对应论文或节点") {
    return new KnowledgeClientError("NOT_FOUND", message, { retryable: false });
  }

  static timeout(message = "知识底座服务响应超时") {
    return new KnowledgeClientError("TIMEOUT", message, { retryable: true });
  }

  static unavailable(message = "知识底座服务暂不可用") {
    return new KnowledgeClientError("UPSTREAM_UNAVAILABLE", message, { retryable: true });
  }

  static invalidArgument(message = "检索参数不合法") {
    return new KnowledgeClientError("INVALID_ARGUMENT", message, { retryable: false });
  }
}
