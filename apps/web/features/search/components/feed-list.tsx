"use client";

import { useEffect, useMemo, useRef } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { discoveryQueryRetry } from "@/clients/backend/discovery";
import {
  fetchDiscoveryFeedPage,
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

/** Single snapshot-backed discovery feed with cursor-based infinite loading. */
export function FeedList() {
  const sentinelRef = useRef<HTMLDivElement>(null);
  const {
    data,
    isPending,
    isError,
    isFetchingNextPage,
    isFetchNextPageError,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ["discovery-papers"],
    queryFn: ({ pageParam }) => fetchDiscoveryFeedPage(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.hasMore ? page.nextCursor ?? undefined : undefined,
    staleTime: 10 * 60 * 1000,
    retry: discoveryQueryRetry,
  });

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
        <PaperCard key={paper.id} paper={paper} index={i} />
      ))}
      <div ref={sentinelRef} className="flex min-h-12 items-center justify-center py-2" aria-live="polite">
        {isFetchingNextPage && (
          <span className="text-sm text-muted">正在加载更多论文…</span>
        )}
        {isFetchNextPageError && (
          <div className="text-center" role="alert">
            <p className="text-sm text-muted">后续论文加载失败，已加载内容不受影响。</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => void fetchNextPage()}
            >
              重试加载
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
