"use client";

import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Info, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import {
  conferenceDeadlineSearchParams,
  conferenceQueryRetry,
  fetchConferenceCategories,
  fetchConferenceDeadlines,
} from "@/clients/backend/conferences";
import { ConferenceCard } from "./conference-card";
import { ConferenceFilterPanel } from "./conference-filter-panel";
import { useNow } from "@/features/submit/hooks/use-now";
import {
  EMPTY_CONFERENCE_FILTERS,
  toDeadlineQuery,
  type ConferenceFilterState,
} from "@/features/submit/services/conference-filters";

function ListLoading() {
  return (
    <div className="space-y-6" aria-label="正在加载会议截稿信息">
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index} className="h-[230px] animate-pulse rounded-2xl bg-card shadow-card" />
      ))}
    </div>
  );
}

/** 会议截稿浏览区 —— 筛选条件经 BFF 交给 FastAPI，列表内所有倒计时共享一个时钟 */
export function ConferenceBrowser() {
  const [filters, setFilters] = useState<ConferenceFilterState>(EMPTY_CONFERENCE_FILTERS);
  const debouncedQ = useDebounce(filters.q, 300);
  const query = useMemo(
    () => toDeadlineQuery({ ...filters, q: debouncedQ }),
    [filters, debouncedQ],
  );
  const now = useNow();

  const categories = useQuery({
    queryKey: ["conference-categories"],
    queryFn: ({ signal }) => fetchConferenceCategories(signal),
    staleTime: 60 * 60 * 1000,
    retry: conferenceQueryRetry,
  });
  const deadlines = useQuery({
    queryKey: ["conference-deadlines", conferenceDeadlineSearchParams(query).toString()],
    queryFn: ({ signal }) => fetchConferenceDeadlines(query, signal),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000,
    retry: conferenceQueryRetry,
  });

  const categoryNames = useMemo(
    () => new Map((categories.data?.items ?? []).map((item) => [item.id, item.name])),
    [categories.data],
  );
  const data = deadlines.data;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-[420px]">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <Input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="搜索会议简称、全称，如 NeurIPS、Computer Vision"
            maxLength={100}
            aria-label="搜索会议"
            className="pl-10"
          />
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-pressed={filters.includeClosed}
            onClick={() => setFilters((prev) => ({ ...prev, includeClosed: !prev.includeClosed }))}
            className={cn(
              "h-8 cursor-pointer rounded-full px-4 text-[13px] transition-colors",
              filters.includeClosed ? "bg-primary font-medium text-white" : "bg-sidebar text-muted hover:text-ink-2",
            )}
          >
            显示已截止
          </button>
          <span className="text-sm text-faint" aria-live="polite">
            {data ? `${data.total} 个会议` : ""}
          </span>
        </div>
      </div>

      {data && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-faint">
          <Info className="size-3.5 shrink-0" />
          数据快照 {data.data_as_of}，来源
          <a href={data.source_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            ccf-deadlines
          </a>
          ；时间已换算为你的本地时区，截稿信息以会议官网为准。
        </p>
      )}

      <div className="mt-5 grid items-start gap-6 xl:grid-cols-[300px_1fr]">
        <ConferenceFilterPanel
          filters={filters}
          categories={categories.data?.items}
          onChange={setFilters}
          onReset={() => setFilters((prev) => ({ ...EMPTY_CONFERENCE_FILTERS, includeClosed: prev.includeClosed }))}
        />

        <div className={cn("space-y-6 transition-opacity", deadlines.isPlaceholderData && "opacity-60")}>
          {deadlines.isPending ? (
            <ListLoading />
          ) : deadlines.isError && !data ? (
            <div className="rounded-2xl bg-card px-6 py-12 text-center shadow-card" role="alert">
              <p className="text-sm font-medium text-ink">会议截稿信息加载失败</p>
              <p className="mt-2 text-sm text-muted">服务暂时不可用，请稍后重试。</p>
              <Button variant="outline" size="sm" className="mt-4" onClick={() => void deadlines.refetch()}>
                重新加载
              </Button>
            </div>
          ) : data && data.items.length === 0 ? (
            <div className="rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">
              暂无符合条件的{filters.includeClosed ? "" : "未截止"}会议
              {!filters.includeClosed && (
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-3"
                  onClick={() => setFilters((prev) => ({ ...prev, includeClosed: true }))}
                >
                  显示已截止的会议
                </Button>
              )}
            </div>
          ) : (
            data?.items.map((conference, index) => (
              <ConferenceCard
                key={conference.id}
                conference={conference}
                categoryName={categoryNames.get(conference.category)}
                // Closed / TBD cannot change as time moves forward: freeze their clock.
                now={conference.status === "open" ? now : deadlines.dataUpdatedAt}
                index={index}
              />
            ))
          )}
        </div>
      </div>
    </>
  );
}
