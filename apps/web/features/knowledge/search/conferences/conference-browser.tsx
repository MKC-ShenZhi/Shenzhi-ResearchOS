"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowUpRight } from "lucide-react";
import type { KnowledgeConference } from "@/clients/knowledge";
import { SearchNavigationLink } from "@/components/common/layout/search-navigation-link";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { useSearchRestorationScope } from "@/hooks/use-search-restoration";
import { KnowledgeSearchHero } from "../components/search-hero";
import { KnowledgeResultCard } from "../components/result-card";
import { KnowledgeSearchSkeleton } from "../components/search-states";
import { KnowledgeSearchPagination } from "../components/search-pagination";
import { rememberSearchScroll, saveCurrentSearchScroll, useSearchScrollRestoration } from "../use-search-scroll-restoration";
import { LibraryModeNav } from "./library-mode-nav";
import { ConferenceEmpty, ConferenceError, ConferenceSkeleton } from "./conference-states";
import { ConferenceCarousel } from "./conference-carousel";
import { conferenceQueryOptions, paperBrowseQueryOptions } from "./conference-queries";
import { PAPER_BROWSE_PAGE_SIZE, readPaperBrowseState, resolveConference, resolveConferenceYear } from "./conference-state";
import { normalizeConferenceBrowse, updateConferenceBrowse } from "./conference-navigation";

const EMPTY_CONFERENCES: KnowledgeConference[] = [];

export function ConferenceBrowser() {
  const router = useRouter();
  const params = useSearchParams();
  const [query, setQuery] = useState("");
  const state = readPaperBrowseState(params);
  const conferences = useQuery(conferenceQueryOptions());
  const items = conferences.data?.items ?? EMPTY_CONFERENCES;
  const selected = resolveConference(items, state.conference);
  const year = selected ? resolveConferenceYear(selected, state.year) : 0;
  const page = year === state.year ? state.page : 1;
  useEffect(() => {
    normalizeConferenceBrowse(items);
  }, [items, params]);

  return <div className="mx-auto max-w-[1120px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <KnowledgeSearchHero initialQuery={query} onQueryChange={setQuery} onSearch={(text) => {
      if (text.trim()) router.push(`/knowledge/search?q=${encodeURIComponent(text.trim())}&page=1`);
    }} />
    <LibraryModeNav mode="conference" />
    <section aria-labelledby="conference-navigation-title">
      <div className="mb-2 flex items-center justify-between gap-4">
        <h2 id="conference-navigation-title" className="text-base font-semibold text-ink">会议导览</h2>
        <SearchNavigationLink href="/knowledge/search/conferences" className="flex min-h-10 items-center gap-1 text-xs font-medium text-primary">更多会议 <ArrowUpRight className="size-3.5" /></SearchNavigationLink>
      </div>
      {conferences.isPending ? <ConferenceSkeleton compact /> : conferences.isError && !conferences.data ? (
        <ConferenceError error={conferences.error} onRetry={() => void conferences.refetch()} />
      ) : items.length === 0 ? <ConferenceEmpty>暂无收录会议，请稍后再来。</ConferenceEmpty> : <>
        {conferences.isError && <p role="status" className="mb-3 text-sm text-muted">会议更新失败，正在展示缓存数据。<button className="ml-2 text-primary" onClick={() => void conferences.refetch()}>重试</button></p>}
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <div className="flex min-h-40 flex-col justify-between rounded-xl border border-primary/20 bg-primary-soft p-4">
            <div><p className="text-[11px] font-medium text-primary">当前会议</p><h3 className="mt-2 break-words text-xl font-semibold text-ink">{selected?.name ?? state.conference}</h3></div>
            {selected ? <dl className="mt-4 grid grid-cols-2 gap-3">
              <div><dt className="text-[11px] text-muted">已收录论文</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{selected.paperCount.toLocaleString()}</dd></div>
              <div><dt className="text-[11px] text-muted">已收录年份</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{selected.yearCount}</dd></div>
            </dl> : <p className="mt-4 text-xs text-muted">未找到该会议，请选择其他会议或进入全部会议目录。</p>}
          </div>
          <ConferenceCarousel items={items} onSelect={(conference) => updateConferenceBrowse(items, { conference: conference.name })} />
        </div>
        {selected && <>
          <ConferenceYears key={selected.name} conference={selected} year={year} onSelect={(value) => updateConferenceBrowse(items, { year: value })} />
          {year ? <ConferencePapers conference={selected.name} year={year} page={page} onPageChange={(nextPage) => updateConferenceBrowse(items, { page: nextPage })} /> : <ConferenceEmpty>该会议暂未提供可浏览的收录年份。</ConferenceEmpty>}
        </>}
      </>}
    </section>
  </div>;
}

function ConferenceYears({ conference, year, onSelect }: { conference: KnowledgeConference; year: number; onSelect: (year: number) => void }) {
  const [expanded, setExpanded] = useState(false);
  const visibleYears = expanded ? conference.years : conference.years.slice(0, 8);
  // A restored year stays visible even when it is outside the collapsed range.
  const years = visibleYears.includes(year) || !year ? visibleYears : [...visibleYears, year];
  return <nav aria-label="收录年份" className="my-4 flex flex-wrap items-center gap-1.5">
    <span className="mr-1.5 text-xs text-muted">收录年份</span>
    {years.map((value) => <button key={value} type="button" aria-pressed={year === value} onClick={() => onSelect(value)} className={`min-h-10 rounded-lg px-3 text-xs sm:min-h-9 ${year === value ? "bg-primary text-primary-foreground" : "border border-line bg-card text-muted hover:text-primary"}`}>{value}</button>)}
    {conference.years.length > 8 && <button type="button" aria-expanded={expanded} className="min-h-10 px-2 text-xs text-primary sm:min-h-9" onClick={() => setExpanded((value) => !value)}>{expanded ? "收起年份" : "更多年份"}</button>}
  </nav>;
}

function ConferencePapers({ conference, year, page, onPageChange }: { conference: string; year: number; page: number; onPageChange: (page: number) => void }) {
  const returnTo = useCurrentInternalPath();
  const scope = useSearchRestorationScope();
  const query = useQuery(paperBrowseQueryOptions({ conference, year, limit: PAPER_BROWSE_PAGE_SIZE, offset: (page - 1) * PAPER_BROWSE_PAGE_SIZE }));
  useSearchScrollRestoration(returnTo, Boolean(query.data?.results.length), scope);
  if (query.isPending) return <KnowledgeSearchSkeleton count={4} />;
  if (query.isError && !query.data) return <ConferenceError error={query.error} onRetry={() => void query.refetch()} />;
  const data = query.data!;
  return <div className="space-y-4" onClickCapture={(event) => rememberSearchScroll(event, returnTo, scope)}>
    <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
      <h2 className="font-medium text-ink">{conference} · {year}</h2>
      <p aria-live="polite">共 {data.total.toLocaleString()} 篇 · 第 {page} 页{query.isFetching ? " · 更新中…" : ""}</p>
    </div>
    {query.isError && <p role="status" className="text-sm text-muted">论文更新失败，正在展示缓存数据。<button className="ml-2 text-primary" onClick={() => void query.refetch()}>重试</button></p>}
    {data.results.length ? data.results.map((hit, index) => <KnowledgeResultCard key={hit.id} hit={hit} index={index} returnTo={returnTo} onNavigate={() => saveCurrentSearchScroll(returnTo, scope)} />) : <ConferenceEmpty>{page > 1 ? "该页暂无论文，请返回上一页或第一页。" : "该会议在所选年份暂无论文，请切换年份。"}</ConferenceEmpty>}
    <KnowledgeSearchPagination page={page} hasMore={data.offset + data.limit < data.total} onPageChange={onPageChange} />
  </div>;
}
