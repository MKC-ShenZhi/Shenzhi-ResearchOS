"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/common/layout/app-shell";
import type { KnowledgeSearchParams } from "@/clients/knowledge";
import { KnowledgeFilterPanel, type KnowledgeFilters } from "./components/filter-panel";
import { KnowledgeResultsSection } from "./components/results-section";
import { KnowledgeSearchHero } from "./components/search-hero";

const EMPTY_FILTERS: KnowledgeFilters = {
  yearFrom: null,
  yearTo: null,
  venue: [],
  author: [],
  keyword: [],
  subject: [],
};

/**
 * 论文检索页 `/knowledge/search` —— 知识底座 · 论文搜索。
 *
 * 业务链路：页面 → KnowledgeClient 接口 → Next.js BFF → FastAPI。
 * 页面只依赖 clients/knowledge 的契约类型与 Client 工厂。
 */
export function KnowledgeSearchPage({ initialQuery = "" }: { initialQuery?: string }) {
  const router = useRouter();

  const [query, setQuery] = useState(initialQuery);
  const [committedQuery, setCommittedQuery] = useState(initialQuery);
  const [filters, setFilters] = useState<KnowledgeFilters>(EMPTY_FILTERS);

  /** 提交搜索：更新查询词并同步 URL */
  const submitSearch = (q: string) => {
    const text = q.trim();
    setCommittedQuery(text);
    const next = new URLSearchParams();
    if (text) next.set("q", text);
    router.replace(`/knowledge/search?${next.toString()}`);
  };

  const searchParamsForQuery: KnowledgeSearchParams | null = useMemo(() => {
    if (!committedQuery) return null;
    return {
      query: committedQuery,
      topK: 20,
      yearFrom: filters.yearFrom,
      yearTo: filters.yearTo,
      venue: filters.venue,
      author: filters.author,
      keyword: filters.keyword,
      subject: filters.subject,
    };
  }, [committedQuery, filters]);

  return (
    <AppShell>
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
              onChange={setFilters}
              disabled={!committedQuery}
            />
          </aside>

          {/* 结果区 */}
          <main className="min-w-0 flex-1">
            {searchParamsForQuery ? (
              <KnowledgeResultsSection
                params={searchParamsForQuery}
                returnTo={`/knowledge/search?q=${encodeURIComponent(committedQuery)}`}
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
    </AppShell>
  );
}
