"use client";

import { useEffect, useRef } from "react";
import { LoaderCircle, RotateCw } from "lucide-react";
import { KnowledgeClientError } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { KnowledgeResultCard } from "@/features/knowledge/search/components/result-card";
import {
  KnowledgeSearchEmpty,
  KnowledgeSearchError,
  KnowledgeSearchSkeleton,
} from "@/features/knowledge/search/components/search-states";
import { useTopicPapers } from "./use-topic-papers";
import { canAutoLoadTopicPapers, TOPIC_PAPER_RESULT_LIMIT } from "./topic-paper-query";

export function TopicRelatedPapers({
  topicId,
  subjectQuery,
}: {
  topicId: string;
  subjectQuery: string;
}) {
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef(false);
  const returnTo = useCurrentInternalPath();
  const {
    papers,
    total,
    data,
    error,
    isPending,
    isError,
    isFetching,
    isFetchNextPageError,
    limitReached,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useTopicPapers(topicId, subjectQuery);

  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !canAutoLoadTopicPapers({ hasNextPage, isFetching, isError })) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting && !loadingRef.current) {
          loadingRef.current = true;
          void fetchNextPage({ cancelRefetch: false }).finally(() => {
            loadingRef.current = false;
          });
        }
      },
      { rootMargin: "320px 0px" },
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetching, isError]);

  const clientError =
    error instanceof KnowledgeClientError
      ? error
      : new KnowledgeClientError("UNKNOWN", "相关论文加载失败");

  return (
    <section aria-labelledby="topic-related-papers" className="mt-7">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h2
            id="topic-related-papers"
            className="text-xl font-semibold tracking-tight text-foreground"
          >
            相关论文
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {data
              ? "共 " + total.toLocaleString() + " 篇论文"
              : isError ? "暂时无法统计相关论文" : "正在统计相关论文"}
          </p>
        </div>
      </div>

      {isPending && !data ? (
        <KnowledgeSearchSkeleton count={4} />
      ) : isError && !data ? (
        <KnowledgeSearchError
          error={clientError}
          onRetry={() => void refetch()}
        />
      ) : papers.length === 0 ? (
        <KnowledgeSearchEmpty query={subjectQuery} />
      ) : (
        <div className="space-y-4">
          {papers.map((paper, index) => (
            <KnowledgeResultCard
              key={paper.id}
              hit={paper}
              index={index}
              returnTo={returnTo}
            />
          ))}

          <div
            ref={loadMoreRef}
            className="flex min-h-20 items-center justify-center border-t border-line pt-4 text-sm text-muted-foreground"
          >
            {isFetchingNextPage ? (
              <span className="inline-flex items-center gap-2">
                <LoaderCircle className="size-4 animate-spin" />
                正在加载更多论文
              </span>
            ) : isFetchNextPageError ? (
              <div className="flex flex-wrap items-center justify-center gap-3" role="alert">
                <span>下一页加载失败，已加载的论文仍可查看。</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isFetching}
                  onClick={() => void fetchNextPage({ cancelRefetch: false })}
                >
                  <RotateCw className="size-3.5" />
                  重试下一页
                </Button>
              </div>
            ) : isError ? (
              <Button type="button" variant="outline" size="sm" disabled={isFetching} onClick={() => void refetch()}>
                <RotateCw className="size-3.5" />重新加载
              </Button>
            ) : hasNextPage ? (
              <span>继续向下滚动加载更多</span>
            ) : (
              <span>{limitReached
                ? `已达到当前接口展示上限（${TOPIC_PAPER_RESULT_LIMIT.toLocaleString()} 篇），仍有论文未展示。`
                : papers.length < total
                  ? "检索接口暂未返回更多论文，部分结果尚未展示。"
                  : "已加载全部相关论文"}</span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
