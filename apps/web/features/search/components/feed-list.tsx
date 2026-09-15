"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";
import {
  fetchMvpRandomDiscoveryFeed,
  type DiscoveryFeedTab,
} from "../services/mvp-random-discovery-feed";
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

/** 发现 Feed —— 真实 Knowledge 搜索结果及 loading / error / empty 状态 */
export function FeedList({ tab }: { tab: DiscoveryFeedTab }) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["discovery-feed", tab],
    // TODO(MVP-RANDOM-DISCOVERY-FEED): Replace this queryFn with the real discovery service.
    queryFn: () => fetchMvpRandomDiscoveryFeed(tab),
    staleTime: 5 * 60_000,
    retry: knowledgeQueryRetry,
  });

  if (isPending) return <FeedLoading />;

  if (isError) {
    return (
      <div className="rounded-2xl bg-card px-6 py-12 text-center shadow-card" role="alert">
        <p className="text-sm font-medium text-ink">发现论文加载失败</p>
        <p className="mt-2 text-sm text-muted">知识底座暂时不可用，请稍后重试。</p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => void refetch()}>
          重新加载
        </Button>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="rounded-2xl bg-card px-6 py-12 text-center text-sm text-muted shadow-card">
        当前分类暂未检索到论文，请稍后再试。
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {data.map((paper, i) => (
        <PaperCard key={paper.id} paper={paper} index={i} />
      ))}
    </div>
  );
}
