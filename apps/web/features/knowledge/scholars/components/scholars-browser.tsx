"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { getKnowledgeClient, KnowledgeClientError } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";
import {
  KnowledgeSearchError,
  KnowledgeSearchSkeleton,
} from "@/features/knowledge/search/components/search-states";
import { ScholarCard } from "./scholar-card";

/** Scholar Search 正式入口；不读取原型学者数据。 */
export function ScholarsBrowser() {
  const [query, setQuery] = useState("");
  const [committedQuery, setCommittedQuery] = useState("");
  const { data, isPending, isFetching, isError, error, refetch } = useQuery({
    queryKey: ["knowledge", "scholars", "search", committedQuery],
    queryFn: () => getKnowledgeClient().searchScholars({ query: committedQuery }),
    enabled: committedQuery.length > 0,
    retry: knowledgeQueryRetry,
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCommittedQuery(query.trim());
  };

  const results = data?.results ?? [];

  return (
    <div className="mx-auto w-full max-w-[980px] px-6 py-8 lg:px-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">学者库</h1>
        <p className="mt-1.5 text-sm text-muted">按姓名搜索学者并查看真实论文成果与合作信息</p>
      </header>

      <form onSubmit={submit} className="mt-6 flex gap-3 rounded-2xl bg-card p-4 shadow-card">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">搜索学者姓名</span>
          <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索学者姓名，例如 Geoffrey Hinton"
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
            输入学者姓名开始搜索
          </div>
        ) : isPending || isFetching ? (
          <KnowledgeSearchSkeleton count={4} />
        ) : isError ? (
          <KnowledgeSearchError
            error={error instanceof KnowledgeClientError
              ? error
              : new KnowledgeClientError("UNKNOWN", "学者搜索失败")}
            onRetry={() => void refetch()}
          />
        ) : results.length === 0 ? (
          <div className="rounded-2xl bg-card p-12 text-center shadow-card">
            <p className="text-sm font-medium text-ink-2">未找到与「{committedQuery}」匹配的学者</p>
            <p className="mt-2 text-xs text-faint">请尝试完整姓名或英文姓名</p>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="px-1 text-sm text-muted">
              「{committedQuery}」的学者结果 · {results.length} 位
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              {results.map((scholar) => (
                <ScholarCard key={scholar.id} scholar={scholar} />
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
