"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { useClearSearchRestoration } from "@/hooks/use-search-restoration";
import { knowledgeQueryRetry } from "../../retry";
import { SCHOLAR_PAGE_SIZE, scholarPage } from "../url-state";
import { useScholarProvider } from "../provider";
import { ScholarCard } from "./scholar-card";
import { DemoBadge, ScholarError, ScholarLoading } from "./profile-parts";

export function ScholarsBrowser() {
  const router = useRouter();
  const clearRestoration = useClearSearchRestoration("/knowledge/scholars");
  const searchParams = useSearchParams();
  const committedQuery = searchParams.get("q")?.trim() ?? "";
  const page = scholarPage(searchParams.get("page"));
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
  const canLoad = Boolean(committedQuery || provider.supportsBrowse);
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["scholars-v2", provider.cacheKey, "search", committedQuery, page],
    enabled: canLoad,
    retry: knowledgeQueryRetry,
    staleTime: 120_000,
    queryFn: ({ signal }) => provider.search(committedQuery, signal, { limit: SCHOLAR_PAGE_SIZE, offset: (page - 1) * SCHOLAR_PAGE_SIZE }),
  });

  function navigate(value: string, nextPage = 1) {
    const next = new URLSearchParams();
    // 保留预览主题，其余搜索状态由本功能管理。
    const theme = searchParams.get("theme");
    if (theme) next.set("theme", theme);
    const normalized = value.trim();
    if (!normalized) clearRestoration();
    else next.set("q", normalized);
    if (nextPage > 1 && (normalized || provider.supportsBrowse)) next.set("page", String(nextPage));
    const serialized = next.toString();
    router.push(`/knowledge/scholars${serialized ? `?${serialized}` : ""}`, {
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
    <div className="mx-auto w-full max-w-[1200px] px-5 py-7 sm:px-8 lg:py-8 xl:px-12">
      <header className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <h1 className="text-3xl font-semibold tracking-tight text-ink">
              学者库
            </h1>
            <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
              Researchers
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-muted">
            从学者出发，了解研究与成果。
          </p>
        </div>
        {provider.isDemo ? <DemoBadge /> : null}
      </header>
      <form
        onSubmit={submit}
        role="search"
        className="mt-5 flex items-center gap-2 rounded-lg border border-line bg-card p-1.5 focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-primary/10 sm:gap-3"
      >
        <Search
          aria-hidden="true"
          className="ml-2 size-5 shrink-0 text-muted sm:ml-3"
        />
        <label className="min-w-0 flex-1">
          <span className="sr-only">{provider.isPreview ? "搜索姓名或机构" : "搜索学者姓名"}</span>
          <input
            type="search"
            maxLength={200}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={provider.isPreview ? "搜索姓名、别名或机构" : "搜索中文或英文姓名"}
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
        <Button type="submit" disabled={!query.trim()} className="h-10 px-4 sm:px-6">
          搜索
        </Button>
      </form>
      <div className="mb-4 mt-6 flex items-center justify-between gap-3 border-b border-line pb-3">
        <h2 className="flex items-center gap-2 text-sm font-medium text-ink">
          {committedQuery ? "搜索结果" : provider.supportsBrowse ? "浏览学者" : "搜索学者"}
        </h2>
        <p aria-live="polite" className="text-xs text-muted">
          {data ? `${data.items.length} 位学者 · 第 ${page} 页${data.total != null ? ` · 共 ${data.total} 位` : ""}` : !canLoad ? "请输入姓名" : isError ? "加载失败" : "正在加载…"}
        </p>
      </div>
      {!canLoad ? (
        <div role="status" className="rounded-2xl border border-dashed border-line p-12 text-center text-sm text-muted">
          输入中文或英文姓名，搜索真实学者。当前数据源暂不支持无关键词浏览。
        </div>
      ) : isPending && !data ? (
        <ScholarLoading cards />
      ) : isError && !data ? (
        <ScholarError onRetry={() => void refetch()} />
      ) : data?.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-card/50 px-5 py-16 text-center">
          <Search className="mx-auto size-7 text-faint" />
          <p className="mt-4 break-words text-sm font-medium text-ink">
            {committedQuery ? `未找到与「${committedQuery}」匹配的学者` : "这一页暂无学者"}
          </p>
          <p className="mt-2 text-sm text-muted">{committedQuery ? "请尝试其他关键词" : "请返回上一页"}</p>
          <Button variant="outline" className="mt-5" onClick={clear}>
            {committedQuery ? "清空搜索" : "返回第一页"}
          </Button>
        </div>
      ) : (
        <div className="grid items-stretch gap-4 md:grid-cols-2">
          {data?.items.map((scholar) => (
            <ScholarCard
              key={scholar.scholar_id}
              scholar={scholar}
              returnTo={returnTo}
              preview={provider.isPreview}
            />
          ))}
        </div>
      )}
      {canLoad && data ? (
        <nav aria-label="学者列表分页" className="mt-6 flex flex-wrap items-center justify-center gap-4">
          <Button variant="outline" disabled={page <= 1} onClick={() => navigate(committedQuery, page - 1)}>上一页</Button>
          <span className="text-sm text-muted">第 {page} 页</span>
          <Button variant="outline" disabled={!data.has_more} onClick={() => navigate(committedQuery, page + 1)}>下一页</Button>
        </nav>
      ) : null}
      <p className="mt-6 text-center text-xs leading-6 text-muted">
        {provider.isPreview ? "本地学者数据预览" : provider.isDemo ? "人物、机构与学术统计均为虚构演示内容，未经知识底座验证。" : "数据来自知识底座；检索可能包含姓名片段匹配，请核对学者身份。未提供字段显示暂无数据。"}
      </p>
    </div>
  );
}
