"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, UsersRound, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { useClearSearchRestoration } from "@/hooks/use-search-restoration";
import { useScholarProvider } from "../provider";
import { ScholarCard } from "./scholar-card";
import { DemoBadge, ScholarError, ScholarLoading } from "./profile-parts";

export function ScholarsBrowser() {
  const router = useRouter();
  const clearRestoration = useClearSearchRestoration("/knowledge/scholars");
  const searchParams = useSearchParams();
  const committedQuery = searchParams.get("q")?.trim() ?? "";
  const returnTo = useCurrentInternalPath();
  const provider = useScholarProvider();
  const [queryDraft, setQueryDraft] = useState({
    source: committedQuery,
    value: committedQuery,
  });
  const query =
    queryDraft.source === committedQuery ? queryDraft.value : committedQuery;
  const setQuery = (value: string) =>
    setQueryDraft({ source: committedQuery, value });
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["scholars-v2", provider.cacheKey, "search", committedQuery],
    queryFn: ({ signal }) => provider.search(committedQuery, signal),
  });

  function navigate(value: string) {
    const next = new URLSearchParams();
    // 保留预览主题，其余搜索状态由本功能管理。
    const theme = searchParams.get("theme");
    if (theme) next.set("theme", theme);
    const normalized = value.trim();
    if (!normalized) clearRestoration();
    else next.set("q", normalized);
    const serialized = next.toString();
    router.replace(`/knowledge/scholars${serialized ? `?${serialized}` : ""}`, {
      scroll: false,
    });
    setQueryDraft({ source: normalized, value: normalized });
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate(query);
  }
  function clear() {
    setQuery("");
    navigate("");
  }

  return (
    <div className="mx-auto w-full max-w-[1200px] px-5 py-8 sm:px-8 lg:py-12 xl:px-12">
      <header className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary">
            Researchers
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">
            学者库
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted">
            从学者出发，了解研究与成果。
          </p>
        </div>
        <DemoBadge />
      </header>
      <form
        onSubmit={submit}
        role="search"
        className="mt-7 flex items-center gap-2 rounded-xl border border-line bg-card p-2 shadow-card focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-primary/10 sm:gap-3"
      >
        <Search
          aria-hidden="true"
          className="ml-2 size-5 shrink-0 text-muted sm:ml-3"
        />
        <label className="min-w-0 flex-1">
          <span className="sr-only">搜索学者姓名</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索中文或英文姓名"
            className="h-10 w-full min-w-0 bg-transparent text-sm text-ink outline-none placeholder:text-faint [&::-webkit-search-cancel-button]:hidden"
          />
        </label>
        {query || committedQuery ? (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label="清空搜索"
            onClick={clear}
          >
            <X />
          </Button>
        ) : null}
        <Button type="submit" className="h-10 px-4 sm:px-6">
          搜索
        </Button>
      </form>
      <div className="mb-5 mt-8 flex items-center justify-between gap-3 border-b border-line pb-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-ink">
          <UsersRound aria-hidden="true" className="size-4 text-muted" />
          {committedQuery ? "搜索结果" : "浏览示例学者"}
        </h2>
        <p aria-live="polite" className="text-xs text-muted">
          {data ? `${data.length} 位学者` : isError ? "加载失败" : "正在加载…"}
        </p>
      </div>
      {isPending && !data ? (
        <ScholarLoading cards />
      ) : isError && !data ? (
        <ScholarError onRetry={() => void refetch()} />
      ) : data?.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-card/50 px-5 py-16 text-center">
          <Search className="mx-auto size-7 text-faint" />
          <p className="mt-4 break-words text-sm font-medium text-ink">
            未找到与「{committedQuery}」匹配的学者
          </p>
          <p className="mt-2 text-sm text-muted">请尝试完整姓名或英文姓名</p>
          <Button variant="outline" className="mt-5" onClick={clear}>
            清空搜索，浏览全部
          </Button>
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          {data?.map((scholar) => (
            <ScholarCard
              key={scholar.scholar_id}
              scholar={scholar}
              returnTo={returnTo}
            />
          ))}
        </div>
      )}
      <p className="mt-8 text-center text-xs leading-6 text-muted">
        人物、机构与学术统计均为虚构演示内容，未经知识底座验证。
      </p>
    </div>
  );
}
