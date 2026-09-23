"use client";

import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Search } from "lucide-react";
import { getKnowledgeClient, KnowledgeClientError } from "@/clients/knowledge";
import type { KnowledgeFundingSummary } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";
import { KnowledgeResultCard } from "@/features/knowledge/search/components/result-card";
import {
  KnowledgeSearchEmpty,
  KnowledgeSearchError,
  KnowledgeSearchSkeleton,
} from "@/features/knowledge/search/components/search-states";
import {
  buildFundingUrl,
  type FundingSearchParamsLike,
  readFundingUrlState,
} from "../funding-url-state";

const FUNDING_PAGE_SIZE = 20;

export function FundingBrowser() {
  const searchParams = useSearchParams();
  return <FundingBrowserContent key={searchParams.toString()} searchParams={searchParams} />;
}

function FundingBrowserContent({ searchParams }: { searchParams: FundingSearchParamsLike }) {
  const router = useRouter();
  const { query: urlQuery, fundingId } = readFundingUrlState(searchParams);
  const returnTo = useCurrentInternalPath();
  const [queryDraft, setQueryDraft] = useState({ source: urlQuery, value: urlQuery });
  const [selectedFundingState, setSelectedFundingState] = useState<
    KnowledgeFundingSummary | null | undefined
  >();
  const query = queryDraft.source === urlQuery ? queryDraft.value : urlQuery;
  const committedQuery = urlQuery;
  const setQuery = (value: string) => setQueryDraft({ source: urlQuery, value });

  const fundingQuery = useInfiniteQuery({
    queryKey: ["knowledge", "fundings", committedQuery],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => getKnowledgeClient().searchFundings({
      query: committedQuery,
      limit: FUNDING_PAGE_SIZE,
      offset: pageParam,
    }),
    getNextPageParam: (lastPage, pages) =>
      lastPage.results.length < FUNDING_PAGE_SIZE ? undefined : pages.length * FUNDING_PAGE_SIZE,
    retry: knowledgeQueryRetry,
  });

  const fundings = fundingQuery.data?.pages.flatMap((page) => page.results) ?? [];
  const candidateFromList = fundingId
    ? fundings.find((candidate) => candidate.id === fundingId) ?? null
    : null;

  const fundingRestoreQuery = useQuery({
    queryKey: ["knowledge", "funding-restore", fundingId],
    queryFn: async () => {
      const response = await getKnowledgeClient().searchFundings({
        query: fundingId!,
        limit: FUNDING_PAGE_SIZE,
        offset: 0,
      });
      return response.results.find((candidate) => candidate.id === fundingId) ?? null;
    },
    enabled: Boolean(fundingId && fundingQuery.isSuccess && !candidateFromList),
    retry: knowledgeQueryRetry,
  });

  const restoredFunding = fundingId
    ? candidateFromList ?? fundingRestoreQuery.data ?? null
    : null;
  const selectedFunding = selectedFundingState === undefined
    ? restoredFunding
    : selectedFundingState;

  const relatedPaperQuery = useQuery({
    queryKey: ["knowledge", "funding-related", selectedFunding?.id, selectedFunding?.name],
    queryFn: () => getKnowledgeClient().searchByFunding(selectedFunding!.name, 20),
    enabled: selectedFunding !== null,
    retry: knowledgeQueryRetry,
  });

  const updateFundingUrl = (nextQuery: string, nextFundingId: string | null) => {
    router.replace(buildFundingUrl(searchParams, nextQuery, nextFundingId), { scroll: false });
  };

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = query.trim();
    setSelectedFundingState(null);
    updateFundingUrl(nextQuery, null);
  };

  const selectFunding = (funding: KnowledgeFundingSummary | null) => {
    setSelectedFundingState(funding);
    updateFundingUrl(committedQuery, funding?.id ?? null);
  };

  const fundingError = fundingQuery.error instanceof KnowledgeClientError
    ? fundingQuery.error
    : new KnowledgeClientError("UNKNOWN", "基金检索失败");
  const relatedPaperError = relatedPaperQuery.error instanceof KnowledgeClientError
    ? relatedPaperQuery.error
    : new KnowledgeClientError("UNKNOWN", "关联论文检索失败");
  const fundingRestoreError = fundingRestoreQuery.error instanceof KnowledgeClientError
    ? fundingRestoreQuery.error
    : new KnowledgeClientError("UNKNOWN", "基金恢复失败");

  return (
    <div className="mx-auto w-full max-w-[1080px] px-6 py-8 lg:px-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">项目基金库</h1>
        <p className="mt-1.5 text-sm text-muted">浏览知识底座中的基金信息，并查看关联论文</p>
      </header>

      <form onSubmit={submit} className="mt-6 flex gap-3 rounded-2xl bg-card p-4 shadow-card">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">搜索基金名称或 ID</span>
          <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索基金名称或 ID…"
            className="h-11 w-full rounded-xl border border-line bg-panel pl-10 pr-4 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
          />
        </label>
        <Button type="submit" className="h-11 px-5" disabled={!query.trim() && committedQuery === ""}>
          <Search />
          搜索
        </Button>
      </form>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
        <section aria-label="基金列表" className="min-w-0">
          <h2 className="mb-3 px-1 text-sm font-semibold text-ink">基金</h2>
          {fundingQuery.isPending ? (
            <KnowledgeSearchSkeleton count={4} />
          ) : fundingQuery.isError ? (
            <KnowledgeSearchError error={fundingError} onRetry={() => void fundingQuery.refetch()} />
          ) : fundings.length === 0 ? (
            <div className="rounded-2xl bg-card p-10 text-center text-sm text-muted shadow-card">
              未找到匹配的基金
            </div>
          ) : (
            <>
              <div className="space-y-2">
                {fundings.map((funding) => {
                  const selected = selectedFunding?.id === funding.id;
                  return (
                    <button
                      key={funding.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => selectFunding(selected ? null : funding)}
                      className={`w-full rounded-xl border px-4 py-3 text-left transition-colors ${
                        selected
                          ? "border-primary bg-primary-soft"
                          : "border-transparent bg-card shadow-card hover:border-line"
                      }`}
                    >
                      <p className="truncate text-sm font-semibold text-ink">{funding.name}</p>
                      <p className="mt-1 text-xs text-muted">关联论文 {funding.paperCount} 篇</p>
                    </button>
                  );
                })}
              </div>
              {fundingQuery.hasNextPage && (
                <Button
                  type="button"
                  variant="outline"
                  className="mt-4 w-full"
                  disabled={fundingQuery.isFetchingNextPage}
                  onClick={() => void fundingQuery.fetchNextPage()}
                >
                  {fundingQuery.isFetchingNextPage ? "加载中…" : "加载更多"}
                </Button>
              )}
            </>
          )}
        </section>

        <section aria-label="基金关联论文" className="min-w-0">
          {!selectedFunding ? (
            fundingRestoreQuery.isError ? (
              <KnowledgeSearchError
                error={fundingRestoreError}
                onRetry={() => void fundingRestoreQuery.refetch()}
              />
            ) : (
              <div className="flex min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-line bg-card/40 px-6 text-center text-sm text-muted">
                {fundingId && fundingQuery.isSuccess && fundingRestoreQuery.isPending
                  ? "正在恢复基金…"
                  : "选择一个基金查看关联论文"}
              </div>
            )
          ) : (
            <>
              <header className="mb-4">
                <h2 className="truncate text-lg font-semibold text-ink">{selectedFunding.name}</h2>
                <p className="mt-1 text-sm text-muted">关联论文</p>
              </header>
              {relatedPaperQuery.isPending ? (
                <KnowledgeSearchSkeleton count={3} />
              ) : relatedPaperQuery.isError ? (
                <KnowledgeSearchError
                  error={relatedPaperError}
                  onRetry={() => void relatedPaperQuery.refetch()}
                />
              ) : relatedPaperQuery.data?.results.length === 0 ? (
                <KnowledgeSearchEmpty query={selectedFunding.name} />
              ) : (
                <div className="space-y-4">
                  {relatedPaperQuery.data?.results.map((paper, index) => (
                    <KnowledgeResultCard
                      key={paper.id}
                      hit={paper}
                      index={index}
                      returnTo={returnTo}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
