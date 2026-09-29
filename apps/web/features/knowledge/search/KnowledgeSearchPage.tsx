"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import type { KnowledgeSearchParams } from "@/clients/knowledge";
import { KnowledgeFilterPanel } from "./components/filter-panel";
import { KnowledgeResultsSection } from "./components/results-section";
import { KnowledgeSearchHero } from "./components/search-hero";
import {
  KNOWLEDGE_SEARCH_PAGE_SIZE,
  knowledgeSearchOffset,
} from "./pagination";
import {
  buildKnowledgeSearchUrl,
  readKnowledgeSearchUrlState,
  type KnowledgeFilters,
} from "./search-url-state";
import {
  cancelObsoleteKnowledgeSearches,
  startKnowledgeSearch,
} from "./search-query-resource";

const KNOWLEDGE_SEARCH_PREFETCH_DELAY_MS = 700;

function createSearchParams(
  query: string,
  filters: KnowledgeFilters,
  page: number,
): KnowledgeSearchParams | null {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) return null;
  return {
    query: normalizedQuery,
    topK: KNOWLEDGE_SEARCH_PAGE_SIZE,
    offset: knowledgeSearchOffset(page),
    yearFrom: filters.yearFrom,
    yearTo: filters.yearTo,
    venue: filters.venue,
    author: filters.author,
    keyword: filters.keyword,
    subject: filters.subject,
  };
}

/**
 * 论文库 `/knowledge/search` —— 保留知识底座论文搜索能力。
 *
 * 业务链路：页面 → KnowledgeClient 接口 → Next.js BFF → FastAPI。
 * 页面只依赖 clients/knowledge 的契约类型与 Client 工厂。
 */
function KnowledgeSearchContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const returnTo = useCurrentInternalPath();
  const { query: committedQuery, filters, page } = readKnowledgeSearchUrlState(searchParams);
  const [queryDraft, setQueryDraft] = useState({
    source: committedQuery,
    value: committedQuery,
  });
  const query = queryDraft.source === committedQuery ? queryDraft.value : committedQuery;
  const setQuery = (value: string) => {
    setQueryDraft({ source: committedQuery, value });
    // 输入变化立即废弃旧预取；新请求只会在 debounce 到期后开始。
    void cancelObsoleteKnowledgeSearches(
      queryClient,
      createSearchParams(value, filters, 1),
    );
  };

  const prefetchParams = useMemo(
    () => createSearchParams(query, filters, 1),
    [query, filters],
  );

  useEffect(() => {
    if (!prefetchParams) return;
    const timeout = window.setTimeout(() => {
      void startKnowledgeSearch(queryClient, prefetchParams).catch(() => undefined);
    }, KNOWLEDGE_SEARCH_PREFETCH_DELAY_MS);
    return () => window.clearTimeout(timeout);
  }, [prefetchParams, queryClient]);

  /** 提交搜索：更新查询词并同步 URL */
  const submitSearch = (q: string) => {
    const text = q.trim();
    const nextParams = createSearchParams(text, filters, 1);
    void cancelObsoleteKnowledgeSearches(queryClient, nextParams);
    if (nextParams) {
      // 请求与路由同步启动；相同 debounce 预取会直接复用同一个 in-flight 请求。
      void startKnowledgeSearch(queryClient, nextParams).catch(() => undefined);
    }
    router.replace(buildKnowledgeSearchUrl({ query: text, filters, page: 1 }), {
      scroll: false,
    });
  };

  const searchParamsForQuery: KnowledgeSearchParams | null = useMemo(() => {
    return createSearchParams(committedQuery, filters, page);
  }, [committedQuery, filters, page]);

  const updateFilters = (nextFilters: KnowledgeFilters) => {
    const nextParams = createSearchParams(committedQuery, nextFilters, 1);
    void cancelObsoleteKnowledgeSearches(queryClient, nextParams);
    if (nextParams) {
      void startKnowledgeSearch(queryClient, nextParams).catch(() => undefined);
    }
    router.replace(
      buildKnowledgeSearchUrl({ query: committedQuery, filters: nextFilters, page: 1 }),
      { scroll: false },
    );
  };

  const updatePage = (nextPage: number) => {
    const nextParams = createSearchParams(committedQuery, filters, nextPage);
    void cancelObsoleteKnowledgeSearches(queryClient, nextParams);
    if (nextParams) {
      void startKnowledgeSearch(queryClient, nextParams).catch(() => undefined);
    }
    router.replace(
      buildKnowledgeSearchUrl({ query: committedQuery, filters, page: nextPage }),
      { scroll: false },
    );
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
      <div className="mx-auto max-w-[1120px] px-6 py-8 lg:px-8">
        <KnowledgeSearchHero
          initialQuery={query}
          onQueryChange={setQuery}
          onSearch={submitSearch}
        />

        <div className="mt-6 flex flex-col gap-6 lg:flex-row">
          {/* 筛选栏 */}
          <aside className="w-full shrink-0 lg:w-64">
            <KnowledgeFilterPanel
              filters={filters}
              onChange={updateFilters}
              disabled={!committedQuery}
            />
          </aside>

          {/* 结果区 */}
          <main className="min-w-0 flex-1">
            {searchParamsForQuery ? (
              <KnowledgeResultsSection
                params={searchParamsForQuery}
                returnTo={returnTo}
                page={page}
                onPageChange={updatePage}
              />
            ) : (
              <div className="flex min-h-[320px] flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-card/40 px-6 text-center shadow-card">
                <p className="text-sm font-medium text-ink-2">输入关键词开始检索论文</p>
                <p className="mt-2 max-w-md text-xs leading-relaxed text-faint">
                  支持按年份、会议、作者、关键词与学科筛选；结果通过 Knowledge BFF 获取。
                </p>
              </div>
            )}
          </main>
        </div>
      </div>
  );
}

export function KnowledgeSearchPage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载论文库…</p>}>
      <KnowledgeSearchContent />
    </Suspense>
  );
}
