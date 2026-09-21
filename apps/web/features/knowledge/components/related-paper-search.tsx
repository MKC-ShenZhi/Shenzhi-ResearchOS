"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { Search } from "lucide-react";
import { getKnowledgeClient, KnowledgeClientError } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";
import { KnowledgeResultCard } from "@/features/knowledge/search/components/result-card";
import {
  KnowledgeSearchEmpty,
  KnowledgeSearchError,
  KnowledgeSearchSkeleton,
} from "@/features/knowledge/search/components/search-states";

type RelatedPaperSearchKind = "subject" | "funding";

const COPY = {
  subject: {
    title: "主题库",
    description: "按研究主题探索知识底座中的相关论文",
    placeholder: "搜索研究主题，例如 Agent / RAG / LLM",
    idle: "输入研究主题开始探索相关论文",
    resultPrefix: "主题",
  },
  funding: {
    title: "项目专利基金库",
    description: "按项目、专利或基金名称探索关联科研成果",
    placeholder: "搜索项目 / 专利 / 基金名称",
    idle: "输入项目、专利或基金名称开始探索关联论文",
    resultPrefix: "项目 / 专利 / 基金",
  },
} satisfies Record<RelatedPaperSearchKind, Record<string, string>>;

async function fetchRelatedPapers(kind: RelatedPaperSearchKind, query: string) {
  const client = getKnowledgeClient();
  return kind === "subject"
    ? client.searchBySubject(query, 20)
    : client.searchByFunding(query, 20);
}

export function RelatedPaperSearch({ kind }: { kind: RelatedPaperSearchKind }) {
  const copy = COPY[kind];
  const returnTo = usePathname();
  const [query, setQuery] = useState("");
  const [committedQuery, setCommittedQuery] = useState("");
  const { data, isPending, isFetching, isError, error, refetch } = useQuery({
    queryKey: ["knowledge", kind, committedQuery],
    queryFn: () => fetchRelatedPapers(kind, committedQuery),
    enabled: committedQuery.length > 0,
    retry: knowledgeQueryRetry,
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCommittedQuery(query.trim());
  };

  const results = data?.results ?? [];

  return (
    <div className="mx-auto max-w-[980px] px-6 py-8 lg:px-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">{copy.title}</h1>
        <p className="mt-1.5 text-sm text-muted">{copy.description}</p>
      </header>

      <form onSubmit={submit} className="mt-6 flex gap-3 rounded-2xl bg-card p-4 shadow-card">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">{copy.placeholder}</span>
          <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={copy.placeholder}
            className="h-11 w-full rounded-xl border border-line bg-panel pl-10 pr-4 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
          />
        </label>
        <Button type="submit" className="h-11 px-5" disabled={!query.trim()}>
          <Search />
          搜索
        </Button>
      </form>

      <main className="mt-6">
        {!committedQuery ? (
          <div className="flex min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-line bg-card/40 px-6 text-center text-sm text-muted">
            {copy.idle}
          </div>
        ) : isPending || isFetching ? (
          <KnowledgeSearchSkeleton count={4} />
        ) : isError ? (
          <KnowledgeSearchError
            error={error instanceof KnowledgeClientError
              ? error
              : new KnowledgeClientError("UNKNOWN", "检索失败")}
            onRetry={() => void refetch()}
          />
        ) : results.length === 0 ? (
          <KnowledgeSearchEmpty query={committedQuery} />
        ) : (
          <div className="space-y-4">
            <div className="px-1">
              <p className="text-sm font-medium text-ink">
                {copy.resultPrefix}：{committedQuery}
              </p>
              <p className="mt-1 text-xs text-muted">
                相关论文 · {results.length} 篇
              </p>
            </div>
            {results.map((hit, index) => (
              <KnowledgeResultCard
                key={hit.id}
                hit={hit}
                index={index}
                returnTo={returnTo}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
