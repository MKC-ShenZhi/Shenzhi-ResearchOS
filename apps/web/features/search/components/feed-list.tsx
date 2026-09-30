"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth/auth-provider";
import { recommendationQueryRetry } from "@/clients/backend/recommendations";
import {
  fetchDailyRecommendationFeed,
  readCachedRecommendationFeed,
  recommendationDate,
  type DiscoveryFeedTab,
} from "../services/daily-recommendation-feed";
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

/** 发现 Feed —— ShenZhi 每日推荐及 localStorage stale-while-revalidate。 */
export function FeedList({ tab }: { tab: DiscoveryFeedTab }) {
  const { session, isPending: isIdentityPending } = useAuth();
  const identityKey = isIdentityPending
    ? "pending"
    : session?.user?.id
      ? `user:${session.user.id}`
      : "anonymous";
  const date = recommendationDate();
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["discovery-feed", identityKey, date, tab],
    queryFn: () => fetchDailyRecommendationFeed(tab, identityKey),
    enabled: !isIdentityPending,
    initialData: () => isIdentityPending
      ? undefined
      : readCachedRecommendationFeed(identityKey, tab, date),
    staleTime: 0,
    refetchOnMount: "always",
    retry: recommendationQueryRetry,
  });

  if (isIdentityPending || isPending) return <FeedLoading />;

  if (isError && !data) {
    return (
      <div className="rounded-2xl bg-card px-6 py-12 text-center shadow-card" role="alert">
        <p className="text-sm font-medium text-ink">发现论文加载失败</p>
        <p className="mt-2 text-sm text-muted">推荐服务暂时不可用，请稍后重试。</p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => void refetch()}>
          重新加载
        </Button>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="rounded-2xl bg-card px-6 py-12 text-center text-sm text-muted shadow-card">
        当前分类暂无推荐论文，请稍后再试。
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
