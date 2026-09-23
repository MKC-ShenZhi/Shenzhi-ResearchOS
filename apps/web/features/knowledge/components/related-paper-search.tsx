"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, Search } from "lucide-react";
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

const PAGE_SIZE = 10;
const MAX_PAGE = 100;
const MAX_BROWSABLE_RESULTS = PAGE_SIZE * MAX_PAGE;

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

function normalizePage(value: string | null) {
  const page = Number(value);
  if (!Number.isInteger(page) || page < 1) return 1;
  return Math.min(page, MAX_PAGE);
}

function topicUrl(pathname: string, subject: string, page: number) {
  const params = new URLSearchParams();
  if (subject) params.set("subject", subject);
  if (subject) params.set("page", String(page));
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

async function fetchRelatedPapers(
  kind: RelatedPaperSearchKind,
  query: string,
  page: number,
  signal?: AbortSignal,
) {
  const client = getKnowledgeClient();
  return kind === "subject"
    ? client.searchBySubject(query, (page - 1) * PAGE_SIZE, PAGE_SIZE, signal)
    : client.searchByFunding(query, PAGE_SIZE);
}

export function RelatedPaperSearch({ kind }: { kind: RelatedPaperSearchKind }) {
  const copy = COPY[kind];
  const returnTo = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const subjectFromUrl = searchParams.get("subject")?.trim() ?? "";
  const pageFromUrl = normalizePage(searchParams.get("page"));
  const [query, setQuery] = useState("");
  const [committedQuery, setCommittedQuery] = useState("");
  const activeQuery = kind === "subject" ? subjectFromUrl : committedQuery;
  const { data, isPending, isFetching, isError, error, refetch } = useQuery({
    queryKey: ["knowledge", kind, activeQuery, pageFromUrl],
    queryFn: ({ signal }) => fetchRelatedPapers(kind, activeQuery, pageFromUrl, signal),
    enabled: activeQuery.length > 0,
    retry: knowledgeQueryRetry,
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (kind === "subject") {
      router.push(topicUrl(returnTo, query.trim(), 1));
    } else {
      setCommittedQuery(query.trim());
    }
  };

  const results = data?.results ?? [];
  const total = kind === "subject" && data && "total" in data ? data.total : 0;
  const totalPages = total > 0 ? Math.min(Math.ceil(total / PAGE_SIZE), MAX_PAGE) : 0;
  const page = totalPages > 0 ? Math.min(pageFromUrl, totalPages) : pageFromUrl;
  const goToPage = (nextPage: number) => {
    if (kind !== "subject" || !subjectFromUrl || totalPages === 0) return;
    const boundedPage = Math.max(1, Math.min(nextPage, totalPages, MAX_PAGE));
    router.push(topicUrl(returnTo, subjectFromUrl, boundedPage));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const submitPage = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const requestedPage = Number(new FormData(event.currentTarget).get("page"));
    goToPage(Number.isInteger(requestedPage) ? requestedPage : 1);
  };

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
        {!activeQuery ? (
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
                {copy.resultPrefix}：{activeQuery}
              </p>
              <p className="mt-1 text-xs text-muted">
                共 {total} 篇论文
              </p>
              {total > MAX_BROWSABLE_RESULTS && (
                <p className="mt-1 text-xs text-muted">最多可浏览前 1000 条</p>
              )}
            </div>
            {results.map((hit, index) => (
              <KnowledgeResultCard
                key={hit.id}
                hit={hit}
                index={index}
                returnTo={returnTo}
              />
            ))}
            {kind === "subject" && <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <p className="text-sm text-muted">第 {page} / {totalPages} 页</p>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="icon" aria-label="首页" onClick={() => goToPage(1)} disabled={page <= 1 || isFetching}>
                  <ChevronsLeft />
                </Button>
                <Button variant="outline" size="icon" aria-label="上一页" onClick={() => goToPage(page - 1)} disabled={page <= 1 || isFetching}>
                  <ChevronLeft />
                </Button>
                <form onSubmit={submitPage} className="flex items-center gap-2">
                  <label htmlFor="topic-page" className="sr-only">页码</label>
                  <input
                    key={page}
                    id="topic-page"
                    name="page"
                    type="number"
                    min={1}
                    max={totalPages}
                    defaultValue={page}
                    className="h-9 w-16 rounded-lg border border-line bg-panel px-2 text-center text-sm text-ink outline-none focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
                  />
                  <Button type="submit" variant="outline" disabled={isFetching}>跳转</Button>
                </form>
                <Button variant="outline" size="icon" aria-label="下一页" onClick={() => goToPage(page + 1)} disabled={page >= totalPages || isFetching}>
                  <ChevronRight />
                </Button>
                <Button variant="outline" size="icon" aria-label="末页" onClick={() => goToPage(totalPages)} disabled={page >= totalPages || isFetching}>
                  <ChevronsRight />
                </Button>
              </div>
            </div>}
          </div>
        )}
      </main>
    </div>
  );
}
