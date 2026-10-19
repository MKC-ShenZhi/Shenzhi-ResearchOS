"use client";

import {
  queryOptions,
  type QueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import {
  getKnowledgeClient,
  type KnowledgeClient,
  type KnowledgeSearchParams,
  type KnowledgeSearchResponse,
} from "../../../clients/knowledge";
import { knowledgeQueryRetry } from "../retry";

/** 搜索结果在两分钟内视为新鲜数据；预取完成后提交不会再次请求。 */
export const KNOWLEDGE_SEARCH_CACHE_TTL_MS = 2 * 60_000;

/**
 * 稍长于新鲜期保留缓存，使过期数据仍可先展示并在后台刷新。
 * 这是页面内存缓存，不会跨浏览器刷新持久化。
 */
export const KNOWLEDGE_SEARCH_CACHE_RETENTION_MS = 3 * 60_000;

const KNOWLEDGE_SEARCH_QUERY_PREFIX = ["knowledge", "search"] as const;

function normalizeValues(values: string[]): string[] {
  return Array.from(
    new Set(values.map((value) => value.trim()).filter((value) => value.length > 0)),
  ).sort((left, right) => (left < right ? -1 : left > right ? 1 : 0));
}

/** 相同语义的筛选条件始终生成相同 key，同时保留完整搜索请求字段。 */
export function normalizeKnowledgeSearchParams(
  params: KnowledgeSearchParams,
): KnowledgeSearchParams {
  return {
    query: params.query.trim(),
    topK: params.topK,
    offset: params.offset ?? 0,
    yearFrom: params.yearFrom,
    yearTo: params.yearTo,
    venue: normalizeValues(params.venue),
    author: normalizeValues(params.author),
    keyword: normalizeValues(params.keyword),
    subject: normalizeValues(params.subject),
  };
}

export function knowledgeSearchCacheKey(params: KnowledgeSearchParams): string {
  return JSON.stringify(normalizeKnowledgeSearchParams(params));
}

export function knowledgeSearchQueryKey(params: KnowledgeSearchParams) {
  return [...KNOWLEDGE_SEARCH_QUERY_PREFIX, knowledgeSearchCacheKey(params)] as const;
}

function isKnowledgeSearchQueryKey(queryKey: QueryKey): boolean {
  return queryKey[0] === KNOWLEDGE_SEARCH_QUERY_PREFIX[0] &&
    queryKey[1] === KNOWLEDGE_SEARCH_QUERY_PREFIX[1];
}

export function knowledgeSearchQueryOptions(
  params: KnowledgeSearchParams,
  client: KnowledgeClient = getKnowledgeClient(),
) {
  const normalizedParams = normalizeKnowledgeSearchParams(params);
  return queryOptions({
    queryKey: knowledgeSearchQueryKey(normalizedParams),
    queryFn: ({ signal }) => client.search(normalizedParams, signal),
    staleTime: KNOWLEDGE_SEARCH_CACHE_TTL_MS,
    gcTime: KNOWLEDGE_SEARCH_CACHE_RETENTION_MS,
    retry: knowledgeQueryRetry,
  });
}

/**
 * 立即开始真实搜索。TanStack Query 会复用相同 key 的 in-flight Promise，
 * 并在新鲜期内直接返回缓存结果。
 */
export function startKnowledgeSearch(
  queryClient: QueryClient,
  params: KnowledgeSearchParams,
  client?: KnowledgeClient,
): Promise<KnowledgeSearchResponse> {
  return queryClient.fetchQuery(knowledgeSearchQueryOptions(params, client));
}

/** 取消除当前条件以外的论文搜索；同 key 的预取/正式搜索不会互相取消。 */
export function cancelObsoleteKnowledgeSearches(
  queryClient: QueryClient,
  currentParams: KnowledgeSearchParams | null,
): Promise<void> {
  const currentKey = currentParams ? knowledgeSearchCacheKey(currentParams) : null;
  return queryClient.cancelQueries({
    predicate: (query) =>
      isKnowledgeSearchQueryKey(query.queryKey) && query.queryKey[2] !== currentKey,
  });
}
