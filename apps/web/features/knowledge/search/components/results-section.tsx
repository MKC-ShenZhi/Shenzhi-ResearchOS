"use client";

import { KnowledgeClientError } from "@/clients/knowledge";
import type { KnowledgeSearchParams } from "@/clients/knowledge";
import { useKnowledgeSearch } from "../use-knowledge-search";
import { KnowledgeResultCard } from "./result-card";
import { KnowledgeSearchPagination } from "./search-pagination";
import {
  KnowledgeSearchEmpty,
  KnowledgeSearchError,
  KnowledgeSearchSkeleton,
} from "./search-states";

/** 论文搜索结果区 —— 负责 loading / empty / error 三种状态的区分 */
export function KnowledgeResultsSection({
  params,
  returnTo,
  page,
  onPageChange,
}: {
  params: KnowledgeSearchParams;
  returnTo: string;
  page: number;
  onPageChange: (page: number) => void;
}) {
  const query = params.query.trim();
  const { data, isPending, isError, error, refetch } = useKnowledgeSearch(params);

  if (query.length === 0) {
    return (
      <p className="rounded-2xl bg-card px-6 py-10 text-center text-sm text-muted shadow-card">
        请输入关键词开始检索论文。
      </p>
    );
  }

  if (isPending && !data) {
    return <KnowledgeSearchSkeleton count={4} />;
  }

  if (isError && !data) {
    const knowledgeError =
      error instanceof KnowledgeClientError
        ? error
        : new KnowledgeClientError("UNKNOWN", error instanceof Error ? error.message : "检索失败");
    return <KnowledgeSearchError error={knowledgeError} onRetry={() => void refetch()} />;
  }

  const results = data?.results ?? [];
  const hasMore = data?.hasMore ?? false;

  if (results.length === 0) {
    return <KnowledgeSearchEmpty query={query} />;
  }

  return (
    <div className="space-y-4">
      <p className="px-1 text-sm text-muted">
        「{query}」的搜索结果 · 第 {page} 页 · 本页
        <span className="font-semibold text-ink"> {results.length}</span> 篇
      </p>
      <div className="space-y-4">
        {results.map((hit, index) => (
          <KnowledgeResultCard key={hit.id} hit={hit} index={index} returnTo={returnTo} />
        ))}
      </div>
      <KnowledgeSearchPagination
        page={page}
        hasMore={hasMore}
        onPageChange={onPageChange}
      />
    </div>
  );
}
