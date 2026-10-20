"use client";

import { useEffect, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Search } from "lucide-react";
import { getKnowledgeClient, KnowledgeClientError } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { useClearSearchRestoration } from "@/hooks/use-search-restoration";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";
import { KnowledgeSearchError } from "@/features/knowledge/search/components/search-states";
import { FundCard } from "./fund-card";
import {
  buildFundingUrl,
  fundingDetailHref,
  type FundingSearchParamsLike,
  readFundingUrlState,
} from "../funding-url-state";

const FUNDING_PAGE_SIZE = 20;
const FUNDING_GRID_CLASS = "grid grid-cols-1 gap-4 lg:grid-cols-2";

export function FundingBrowser() {
  const searchParams = useSearchParams();
  return <FundingBrowserContent key={searchParams.toString()} searchParams={searchParams} />;
}

function FundingBrowserContent({ searchParams }: { searchParams: FundingSearchParamsLike }) {
  const router = useRouter();
  const clearRestoration = useClearSearchRestoration("/knowledge/funding");
  const { query: urlQuery, fundingId } = readFundingUrlState(searchParams);
  const [queryDraft, setQueryDraft] = useState({ source: urlQuery, value: urlQuery });
  const query = queryDraft.source === urlQuery ? queryDraft.value : urlQuery;

  const fundingQuery = useInfiniteQuery({
    queryKey: ["knowledge", "fundings", urlQuery],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => getKnowledgeClient().searchFundings({
      query: urlQuery,
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

  const restoredFunding = candidateFromList ?? fundingRestoreQuery.data ?? null;
  useEffect(() => {
    if (fundingId && restoredFunding) {
      router.replace(fundingDetailHref(restoredFunding.id, restoredFunding.name, urlQuery), { scroll: false });
    }
  }, [fundingId, restoredFunding, router, urlQuery]);

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = query.trim();
    if (!nextQuery) clearRestoration();
    router.replace(buildFundingUrl(searchParams, nextQuery, null), { scroll: false });
  };

  const fundingError = fundingQuery.error instanceof KnowledgeClientError
    ? fundingQuery.error
    : new KnowledgeClientError("UNKNOWN", "基金检索失败");
  const fundingRestoreError = fundingRestoreQuery.error instanceof KnowledgeClientError
    ? fundingRestoreQuery.error
    : new KnowledgeClientError("UNKNOWN", "基金恢复失败");

  return (
    <main className="min-h-screen bg-background px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1180px]">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-ink">项目基金库</h1>
            <p className="mt-1.5 text-sm text-muted">浏览基金项目并探索关联科研论文</p>
          </div>
          <span className="w-fit rounded-full border border-line bg-card px-3 py-1 text-xs font-medium text-muted">
            Mock Demo · 演示数据
          </span>
        </header>

        <form onSubmit={submit} className="mt-6 flex gap-3 rounded-2xl bg-card p-4 shadow-card">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">搜索基金名称或 ID</span>
            <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(event) => setQueryDraft({ source: urlQuery, value: event.target.value })}
              placeholder="搜索基金名称或 ID…"
              className="h-11 w-full rounded-xl border border-line bg-panel pl-10 pr-4 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
            />
          </label>
          <Button type="submit" className="h-11 px-5" disabled={!query.trim() && urlQuery === ""}>
            <Search />
            搜索
          </Button>
        </form>

        {fundingId && !restoredFunding && fundingQuery.isSuccess && fundingRestoreQuery.isError ? (
          <div className="mt-6">
            <KnowledgeSearchError error={fundingRestoreError} onRetry={() => void fundingRestoreQuery.refetch()} />
          </div>
        ) : fundingId && !restoredFunding && fundingRestoreQuery.isSuccess ? (
          <p className="mt-6 rounded-2xl border border-line bg-card px-5 py-4 text-sm text-muted">
            无法恢复此基金信息，请从基金列表中重新选择。
          </p>
        ) : null}

        <section aria-label="基金列表" className="mt-5">
          <div className="mb-3 flex items-center justify-between gap-4 border-b border-line/70 pb-2">
            <h2 className="text-sm font-semibold text-ink">浏览基金项目</h2>
            {fundingQuery.isPending ? (
              <span className="text-xs text-muted">加载中…</span>
            ) : !fundingQuery.isError ? (
              <span className="text-xs tabular-nums text-muted">
                {fundings.length} 个基金
              </span>
            ) : null}
          </div>
          {fundingQuery.isPending ? (
            <div className={FUNDING_GRID_CLASS} aria-busy="true" aria-label="正在加载基金">
              {Array.from({ length: 6 }, (_, index) => (
                <div key={index} className="space-y-3 rounded-2xl bg-card p-5 shadow-card">
                  <div className="flex justify-between gap-3">
                    <div className="size-10 animate-pulse rounded-xl bg-chip" />
                    <div className="size-4 animate-pulse rounded bg-chip" />
                  </div>
                  <div className="space-y-2 pt-1">
                    <div className="h-5 w-5/6 animate-pulse rounded bg-chip" />
                    <div className="h-3 w-2/3 animate-pulse rounded bg-chip" />
                  </div>
                  <div className="space-y-2">
                    <div className="h-4 w-full animate-pulse rounded bg-chip" />
                    <div className="h-4 w-4/5 animate-pulse rounded bg-chip" />
                  </div>
                  <div className="space-y-2">
                    <div className="h-4 w-32 animate-pulse rounded bg-chip" />
                    <div className="h-3 w-48 animate-pulse rounded bg-chip" />
                  </div>
                  <div className="grid grid-cols-3 gap-3 border-t border-line/50 pt-3">
                    <div className="h-8 animate-pulse rounded bg-chip" />
                    <div className="h-8 animate-pulse rounded bg-chip" />
                    <div className="h-8 animate-pulse rounded bg-chip" />
                  </div>
                </div>
              ))}
            </div>
          ) : fundingQuery.isError ? (
            <KnowledgeSearchError error={fundingError} onRetry={() => void fundingQuery.refetch()} />
          ) : fundings.length === 0 ? (
            <div className="rounded-2xl bg-card p-10 text-center text-sm text-muted shadow-card">
              未找到匹配的基金
            </div>
          ) : (
            <>
              <div className={FUNDING_GRID_CLASS}>
                {fundings.map((funding) => (
                  <FundCard key={funding.id} funding={funding} query={urlQuery} />
                ))}
              </div>
              {fundingQuery.hasNextPage ? (
                <div className="mt-6 flex justify-center">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={fundingQuery.isFetchingNextPage}
                    onClick={() => void fundingQuery.fetchNextPage()}
                  >
                    {fundingQuery.isFetchingNextPage ? "加载中…" : "加载更多基金"}
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    </main>
  );
}
