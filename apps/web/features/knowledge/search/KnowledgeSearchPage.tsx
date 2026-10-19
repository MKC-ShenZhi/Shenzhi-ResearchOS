"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { useSearchDraft } from "@/hooks/use-search-draft";
import { SlidersHorizontal } from "lucide-react";
import { useClearSearchRestoration, useSearchRestorationScope } from "@/hooks/use-search-restoration";
import type { KnowledgeSearchParams } from "@/clients/knowledge";
import { KnowledgeFilterPanel } from "./components/filter-panel";
import { KnowledgeResultsSection } from "./components/results-section";
import { KnowledgeSearchHero } from "./components/search-hero";
import { discardSearchScroll } from "./use-search-scroll-restoration";
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
  const scope = useSearchRestorationScope();
  const clearRestoration = useClearSearchRestoration("/knowledge/search");
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const returnTo = useCurrentInternalPath();
  const { query: committedQuery, filters, page } = readKnowledgeSearchUrlState(searchParams);
  const draft = useSearchDraft("/knowledge/search", returnTo, committedQuery);
  const query = draft.value;
  const [filtersOpen, setFiltersOpen] = useState(false);
  const setQuery = (value: string) => {
    draft.set(value);
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
    draft.clear();
    discardSearchScroll(returnTo, scope);
    const text = q.trim();
    if (!text) clearRestoration();
    discardSearchScroll(buildKnowledgeSearchUrl({ query: text, filters, page: 1 }), scope);
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
    discardSearchScroll(returnTo, scope);
    discardSearchScroll(buildKnowledgeSearchUrl({ query: committedQuery, filters: nextFilters, page: 1 }), scope);
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
    discardSearchScroll(returnTo, scope);
    discardSearchScroll(buildKnowledgeSearchUrl({ query: committedQuery, filters, page: nextPage }), scope);
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
      <div className="mx-auto max-w-[1120px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <KnowledgeSearchHero
          initialQuery={query}
          onQueryChange={setQuery}
          onSearch={submitSearch}
          disabled={!draft.ready}
        />

        <button type="button" aria-expanded={filtersOpen} aria-controls="paper-search-filters" onClick={() => setFiltersOpen((open) => !open)} className="mt-4 flex min-h-10 items-center gap-2 rounded-xl border border-line bg-card px-4 text-sm text-ink lg:hidden">
          <SlidersHorizontal className="size-4" />{filtersOpen ? "收起筛选" : "展开筛选"}
        </button>
        <div className="mt-6 flex flex-col gap-6 lg:flex-row">
          {/* 筛选栏 */}
          <aside id="paper-search-filters" className={`${filtersOpen ? "block" : "hidden"} w-full shrink-0 lg:block lg:w-64`}>
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
