"use client";

import { useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { KnowledgeSearchParams } from "@/clients/knowledge";
import {
  cancelObsoleteKnowledgeSearches,
  knowledgeSearchCacheKey,
  knowledgeSearchQueryOptions,
  normalizeKnowledgeSearchParams,
} from "./search-query-resource";

/** 论文搜索唯一入口：缓存、SWR、请求复用和过期请求取消均由 Query Resource 管理。 */
export function useKnowledgeSearch(params: KnowledgeSearchParams) {
  const queryClient = useQueryClient();
  const normalizedParams = useMemo(
    () => normalizeKnowledgeSearchParams(params),
    [params],
  );
  const cacheKey = knowledgeSearchCacheKey(normalizedParams);

  useEffect(() => {
    void cancelObsoleteKnowledgeSearches(queryClient, normalizedParams);
  }, [cacheKey, normalizedParams, queryClient]);

  return useQuery(knowledgeSearchQueryOptions(normalizedParams));
}
