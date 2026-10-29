"use client";

import { useEffect, useMemo, useRef } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth/auth-provider";
import { discoveryQueryRetry } from "@/clients/backend/discovery";
import {
  fetchHomeFeedPage,
  RecommendationFeedExpiredError,
} from "../services/discovery-feed";
import { PaperCard } from "./paper-card";

function FeedLoading() {
  return (
    <div className="space-y-5" aria-label="正在加载发现论文">
      {Array.from({ length: 3 }, (_, index) => (
        <div
          key={index}
          className="h-[220px] animate-pulse rounded-2xl bg-card shadow-card"
        />
      ))}
    </div>
  );
}

/**
 * Snapshot-backed home feed with cursor-based infinite loading.
 *
 * Signed-in users page through one recommendation snapshot; anonymous users
 * (and a failed first recommendation page) use global discovery. Loaded pages
 * are never replaced by a failing next page.
 */
export function FeedList() {
  const { session, isPending: authPending } = useAuth();
  const userId = session?.user.id ?? null;
  const queryClient = useQueryClient();
  const sentinelRef = useRef<HTMLDivElement>(null);
  const queryKey = ["home-feed", userId] as const;
  const {
    data,
    error,
    isPending,
    isError,
    isFetchingNextPage,
    isFetchNextPageError,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => fetchHomeFeedPage(pageParam, userId),
    enabled: !authPending,
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.hasMore ? page.nextCursor ?? undefined : undefined,
    staleTime: 10 * 60 * 1000,
    // A personal refetch creates a new recommendation snapshot; never swap the
    // list under a reader just because the tab regained focus or network.
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: (failureCount, failure) =>
      !(failure instanceof RecommendationFeedExpiredError) && discoveryQueryRetry(failureCount, failure),
  });
  const snapshotExpired = isFetchNextPageError && error instanceof RecommendationFeedExpiredError;

  const papers = useMemo(() => {
    const unique = new Map<string, NonNullable<typeof data>["pages"][number]["items"][number]>();
    for (const page of data?.pages ?? []) {
      for (const paper of page.items) unique.set(paper.id, paper);
    }
    return [...unique.values()];
  }, [data]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasNextPage || isFetchingNextPage || isFetchNextPageError) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void fetchNextPage();
      },
      { rootMargin: "600px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchNextPageError, isFetchingNextPage]);

  if (isPending) return <FeedLoading />;

  if (isError && papers.length === 0) {
    return (
      <div className="rounded-2xl bg-card px-6 py-12 text-center shadow-card" role="alert">
        <p className="text-sm font-medium text-ink">发现论文加载失败</p>
        <p className="mt-2 text-sm text-muted">论文发现服务暂时不可用，请稍后重试。</p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => void refetch()}>
          重新加载
        </Button>
      </div>
    );
  }

  if (papers.length === 0) {
    return (
      <div className="rounded-2xl bg-card px-6 py-12 text-center text-sm text-muted shadow-card">
        当前没有可展示的论文。
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {papers.map((paper, i) => (
        <PaperCard key={`${paper.id}:${paper.recommendationRequestId ?? "global"}`} paper={paper} index={i} />
      ))}
      <div ref={sentinelRef} className="flex min-h-12 items-center justify-center py-2" aria-live="polite">
        {isFetchingNextPage && (
          <span className="text-sm text-muted">正在加载更多论文…</span>
        )}
        {isFetchNextPageError && (
          <div className="text-center" role="alert">
            <p className="text-sm text-muted">
              {snapshotExpired
                ? "推荐列表已过期，刷新后将重新生成推荐。"
                : "后续论文加载失败，已加载内容不受影响。"}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => void (snapshotExpired
                ? queryClient.resetQueries({ queryKey })
                : fetchNextPage())}
            >
              {snapshotExpired ? "刷新推荐" : "重试加载"}
            </Button>
          </div>
        )}
        {!hasNextPage && !isFetchNextPageError && (
          <span className="text-sm text-faint">
            已浏览完全部 {data?.pages[0]?.total ?? papers.length} 篇论文
          </span>
        )}
      </div>
    </div>
  );
}
