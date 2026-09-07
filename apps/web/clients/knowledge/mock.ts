"use client";

import { KnowledgeClientError, type KnowledgeClient } from "./client";
import {
  buildMockGraph,
  MOCK_PAPERS,
  mockPaperDetail,
} from "./mock-data";
import type {
  KnowledgeGraph,
  KnowledgePaperDetail,
  KnowledgePaperHit,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
} from "./types";

/** Mock 可模拟的行为状态 */
export type MockScenario =
  | "success"
  | "zero_results"
  | "timeout"
  | "upstream_unavailable"
  | "not_found";

export interface MockKnowledgeClientOptions {
  /** 显式指定模拟状态；缺省时按 query 关键词推断（便于演示错误态） */
  scenario?: MockScenario;
  /** 模拟网络延迟 ms，默认 400 */
  latencyMs?: number;
}

/** 用于演示错误态的关键词映射：query 命中即触发对应行为 */
const QUERY_SCENARIO: Array<[RegExp, MockScenario]> = [
  [/timeout|超时/i, "timeout"],
  [/unavailable|不可用|宕机/i, "upstream_unavailable"],
  [/notfound|未找到|不存在/i, "not_found"],
  [/empty|无结果/i, "zero_results"],
];

function scenarioFromQuery(query: string): MockScenario | null {
  for (const [pattern, scenario] of QUERY_SCENARIO) {
    if (pattern.test(query)) return scenario;
  }
  return null;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 知识底座 Mock Client。
 *
 * 页面不直接依赖本实现，统一走 KnowledgeClient 接口；
 * 仅在 getKnowledgeClient() 显式配置 source=mock 时启用；正式运行走 BFF。
 */
export class MockKnowledgeClient implements KnowledgeClient {
  private scenario: MockScenario;
  private latencyMs: number;

  constructor(options: MockKnowledgeClientOptions = {}) {
    this.scenario = options.scenario ?? "success";
    this.latencyMs = options.latencyMs ?? 400;
  }

  private async wait(): Promise<void> {
    if (this.latencyMs > 0) await delay(this.latencyMs);
  }

  private throwIfNeeded(query = ""): MockScenario | null {
    const effective = this.scenario === "success" ? scenarioFromQuery(query) : this.scenario;
    if (effective === "timeout") throw KnowledgeClientError.timeout();
    if (effective === "upstream_unavailable") throw KnowledgeClientError.unavailable();
    return effective;
  }

  async search(params: KnowledgeSearchParams): Promise<KnowledgeSearchResponse> {
    await this.wait();
    const scenario = this.throwIfNeeded(params.query);

    const text = params.query.trim().toLowerCase();
    const hits = MOCK_PAPERS.filter((paper) => this.match(paper, text, params))
      .map((paper, index) => {
        const base = text && paper.title.toLowerCase().includes(text) ? 0.85 : 0.5;
        const score = Math.min(1, base + (index % 5) * 0.04);
        return {
          id: paper.id,
          title: paper.title,
          abstract: paper.abstract,
          authors: paper.authors,
          year: paper.year,
          venue: paper.venue,
          keywords: paper.keywords,
          subjects: paper.subjects,
          score,
          rank: 0,
          provenance: { source: "mock" },
        } satisfies KnowledgePaperHit;
      })
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .map((hit, index) => ({ ...hit, rank: index + 1 }));

    if (scenario === "zero_results") return { results: [], hasMore: false };
    const offset = params.offset ?? 0;
    return {
      results: hits.slice(offset, offset + params.topK),
      hasMore: hits.length > offset + params.topK,
    };
  }

  async paper(paperId: string): Promise<KnowledgePaperDetail> {
    await this.wait();
    if (this.scenario === "timeout") throw KnowledgeClientError.timeout();
    if (this.scenario === "upstream_unavailable") throw KnowledgeClientError.unavailable();
    const detail = mockPaperDetail(paperId);
    if (!detail) throw KnowledgeClientError.notFound();
    return detail;
  }

  async graph(paperId: string): Promise<KnowledgeGraph> {
    // Mock 数据仅提供 depth=1 图谱；真实深度由 Bff 客户端透传
    await this.wait();
    if (this.scenario === "timeout") throw KnowledgeClientError.timeout();
    if (this.scenario === "upstream_unavailable") throw KnowledgeClientError.unavailable();
    const graph = buildMockGraph(paperId);
    if (!graph) throw KnowledgeClientError.notFound();
    return graph;
  }

  private match(
    paper: (typeof MOCK_PAPERS)[number],
    text: string,
    params: KnowledgeSearchParams,
  ): boolean {
    if (text && !this.contains(paper, text)) return false;

    if (params.yearFrom !== null && (paper.year === null || paper.year < params.yearFrom)) return false;
    if (params.yearTo !== null && (paper.year === null || paper.year > params.yearTo)) return false;

    if (params.venue.length && !params.venue.includes(paper.venue)) return false;

    const authors = paper.authors.map((a) => a.toLowerCase());
    if (
      params.author.length &&
      !params.author.some((a) => authors.some((author) => author.includes(a.toLowerCase())))
    ) {
      return false;
    }

    const keywords = paper.keywords.map((k) => k.toLowerCase());
    if (
      params.keyword.length &&
      !params.keyword.some((k) => keywords.includes(k.toLowerCase()))
    ) {
      return false;
    }

    const subjects = paper.subjects.map((s) => s.toLowerCase());
    if (
      params.subject.length &&
      !params.subject.some((s) => subjects.includes(s.toLowerCase()))
    ) {
      return false;
    }

    return true;
  }

  private contains(paper: (typeof MOCK_PAPERS)[number], text: string): boolean {
    const haystack = [
      paper.title,
      paper.abstract,
      ...paper.authors,
      ...paper.keywords,
      ...paper.subjects,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(text);
  }
}
