"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { ChevronRight, Search } from "lucide-react";
import type { KnowledgeConference } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { SearchNavigationLink } from "@/components/common/layout/search-navigation-link";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { useClearSearchRestoration, useSearchRestorationScope } from "@/hooks/use-search-restoration";
import { discardSearchScroll, rememberSearchScroll, useSearchScrollRestoration } from "../use-search-scroll-restoration";
import { conferenceQueryOptions } from "./conference-queries";
import { ConferenceEmpty, ConferenceError, ConferenceSkeleton } from "./conference-states";
import { buildConferenceDirectoryUrl, buildPaperBrowseUrl, CONFERENCE_PAGE_SIZE, filterConferences, readConferenceDirectoryState, type ConferenceDirectoryState } from "./conference-state";

function ConferenceDirectoryContent() {
  const searchParams = useSearchParams();
  const returnTo = useCurrentInternalPath();
  const scope = useSearchRestorationScope();
  const clearRestoration = useClearSearchRestoration("/knowledge/search/conferences");
  const state = readConferenceDirectoryState(searchParams);
  const query = useQuery(conferenceQueryOptions());
  const items = query.data?.items ?? [];
  const years = [...new Set(items.flatMap((item) => item.years))].sort((a, b) => b - a);
  const filtered = filterConferences(items, state);
  const pageCount = Math.max(1, Math.ceil(filtered.length / CONFERENCE_PAGE_SIZE));
  const page = Math.min(state.page, pageCount);
  const visible = filtered.slice((page - 1) * CONFERENCE_PAGE_SIZE, page * CONFERENCE_PAGE_SIZE);
  useSearchScrollRestoration(returnTo, Boolean(query.data), scope);
  const update = (next: Partial<ConferenceDirectoryState>) => {
    // This is local filtering: Next's native History integration updates search
    // params without a server navigation. Read the current URL so consecutive
    // keystrokes/filter changes cannot overwrite each other before React renders.
    const current = readConferenceDirectoryState(new URLSearchParams(window.location.search));
    const href = buildConferenceDirectoryUrl({ ...current, page: 1, ...next });
    discardSearchScroll(returnTo, scope);
    discardSearchScroll(href, scope);
    if (href === "/knowledge/search/conferences") clearRestoration();
    window.history.replaceState(null, "", href);
  };

  return <div className="mx-auto max-w-[1120px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8" onClickCapture={(event) => rememberSearchScroll(event, returnTo, scope)}>
    <nav aria-label="面包屑" className="mb-6 flex items-center gap-2 text-sm text-muted">
      <SearchNavigationLink href="/knowledge/search?mode=conference" className="hover:text-primary">论文库</SearchNavigationLink><ChevronRight className="size-3.5" /><span aria-current="page">全部会议</span>
    </nav>
    <header><h1 className="text-2xl font-bold tracking-tight text-ink">全部会议</h1><p className="mt-2 text-sm text-muted">从已收录的学术会议出发，选择年份，发现感兴趣的论文。</p></header>
    <div className="my-6 grid gap-3 rounded-2xl border border-line bg-card p-4 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
      <label className="flex min-w-0 items-center gap-2 rounded-xl border border-line px-3">
        <Search className="size-4 shrink-0 text-faint" /><span className="sr-only">搜索会议名称</span>
        <input value={state.query} onChange={(event) => update({ query: event.target.value })} placeholder="搜索会议名称…" className="h-11 min-w-0 flex-1 bg-transparent text-sm text-ink outline-none" />
      </label>
      <label className="flex items-center gap-2 text-sm text-muted">收录年份
        <select value={state.year} onChange={(event) => update({ year: Number(event.target.value) })} className="h-11 rounded-xl border border-line bg-card px-3 text-ink">
          <option value={0}>全部年份</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}
          {state.year > 0 && !years.includes(state.year) && <option value={state.year}>{state.year}（未收录）</option>}
        </select>
      </label>
      <label className="flex items-center gap-2 text-sm text-muted">排序
        <select value={state.sort} onChange={(event) => update({ sort: event.target.value === "name" ? "name" : "count" })} className="h-11 rounded-xl border border-line bg-card px-3 text-ink"><option value="count">论文数量最多</option><option value="name">会议名称 A–Z</option></select>
      </label>
    </div>
    {query.isPending ? <ConferenceSkeleton /> : query.isError && !query.data ? <ConferenceError error={query.error} onRetry={() => void query.refetch()} /> : <>
      {query.isError && <p role="status" className="mb-4 text-sm text-muted">会议更新失败，正在展示缓存数据。<button className="ml-2 text-primary" onClick={() => void query.refetch()}>重试</button></p>}
      <p role="status" className="mb-4 text-sm text-muted">共 {filtered.length} 条会议记录{filtered.length > 0 && ` · 第 ${page} / ${pageCount} 页`}</p>
      {visible.length ? <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((conference, index) => <DirectoryCard key={`${conference.name}-${index}`} conference={conference} preferredYear={state.year} />)}
      </div> : <ConferenceEmpty>{items.length ? "没有符合条件的会议，请调整搜索或年份。" : "暂无收录会议。"}</ConferenceEmpty>}
      <nav aria-label="会议目录分页" className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Button variant="outline" size="sm" disabled={page === 1} onClick={() => update({ page: page - 1 })}>上一页</Button>
        <label className="flex items-center gap-2 text-sm text-muted">第
          <select aria-label="会议目录页码" value={page} onChange={(event) => update({ page: Number(event.target.value) })} className="h-9 rounded-lg border border-line bg-card px-2 text-ink">{Array.from({ length: pageCount }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}</option>)}</select>
          / {pageCount} 页
        </label>
        <Button variant="outline" size="sm" disabled={page >= pageCount} onClick={() => update({ page: page + 1 })}>下一页</Button>
      </nav>
    </>}
  </div>;
}

function DirectoryCard({ conference, preferredYear }: { conference: KnowledgeConference; preferredYear: number }) {
  const year = conference.years.includes(preferredYear) ? preferredYear : conference.years[0];
  return <article className="flex min-w-0 flex-col rounded-2xl border border-line bg-card p-5 shadow-card">
    <h2 className="break-words text-lg font-semibold text-ink">{year ? <Link href={buildPaperBrowseUrl(conference.name, year)} className="hover:text-primary">{conference.name}</Link> : conference.name}</h2>
    <p className="mt-2 text-sm text-muted">{conference.paperCount.toLocaleString()} 篇论文 · {conference.yearCount} 个收录年份</p>
    <div className="mt-5 flex flex-1 flex-wrap content-start gap-2" aria-label={`${conference.name} 收录年份`}>
      {conference.years.length ? conference.years.map((value) => <Link key={value} href={buildPaperBrowseUrl(conference.name, value)} className={`rounded-lg border px-2.5 py-2 text-xs transition-colors hover:border-primary hover:text-primary ${preferredYear === value ? "border-primary bg-primary-soft text-primary" : "border-line text-muted"}`}>{value}</Link>) : <span className="text-xs text-faint">暂未提供收录年份</span>}
    </div>
    {year && <Link href={buildPaperBrowseUrl(conference.name, year)} className="mt-5 flex min-h-10 items-center justify-between border-t border-line pt-3 text-sm font-medium text-primary">浏览 {year} 年论文 <ChevronRight className="size-4" /></Link>}
  </article>;
}

export function ConferenceDirectoryPage() {
  return <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载会议目录…</p>}><ConferenceDirectoryContent /></Suspense>;
}
