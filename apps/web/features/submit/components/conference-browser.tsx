"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { useDebounce } from "@/hooks/use-debounce";
import {
  conferenceDeadlineSearchParams,
  conferenceQueryRetry,
  fetchConferenceCategories,
  fetchConferenceDeadlines,
  type ConferenceDeadlineDto,
} from "@/clients/backend/conferences";
import { ConferenceCard } from "./conference-card";
import { ConferenceFilterBar } from "./conference-filter-bar";
import { FollowedConferences } from "./followed-conferences";
import { useFollowedConferences } from "@/features/submit/hooks/use-conference-follows";
import { useNow } from "@/features/submit/hooks/use-now";
import {
  EMPTY_CONFERENCE_FILTERS,
  toDeadlineQuery,
  type ConferenceFilterState,
} from "@/features/submit/services/conference-filters";

function ListLoading() {
  return (
    <div className="flex flex-col gap-5" aria-label="正在加载会议截稿信息">
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index} className="h-[230px] animate-pulse rounded-2xl bg-card shadow-card" />
      ))}
    </div>
  );
}

/** 日历事件里的深知链接形如 `/submit?focus=<id>`，进入页面后定位到该会议 */
function initialFocusId(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("focus");
}

/** 会议截稿浏览区 —— 筛选条件经 BFF 交给 FastAPI，列表内所有倒计时共享一个时钟 */
export function ConferenceBrowser() {
  const [filters, setFilters] = useState<ConferenceFilterState>(EMPTY_CONFERENCE_FILTERS);
  const followed = useFollowedConferences();
  const followedOnly = filters.followedOnly && Boolean(followed.userId);
  const debouncedQ = useDebounce(filters.q, 300);
  const query = useMemo(
    () => toDeadlineQuery({ ...filters, followedOnly, q: debouncedQ }),
    [filters, followedOnly, debouncedQ],
  );
  const now = useNow();
  const [focusId, setFocusId] = useState(initialFocusId);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  // 目标会议不在当前筛选结果中时，放宽一次筛选再找
  const focusRelaxed = useRef(false);

  const categories = useQuery({
    queryKey: ["conference-categories"],
    queryFn: ({ signal }) => fetchConferenceCategories(signal),
    staleTime: 60 * 60 * 1000,
    retry: conferenceQueryRetry,
  });
  const deadlines = useQuery({
    // 「只看关注」的结果属于具体账号，键中带上账号避免串号
    queryKey: ["conference-deadlines", followedOnly ? followed.userId : "", conferenceDeadlineSearchParams(query).toString()],
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
  const listSettled = Boolean(data) && !deadlines.isPlaceholderData && debouncedQ === filters.q;

  useEffect(() => {
    // 去掉 URL 中的一次性 focus 参数，刷新页面不再重复定位
    const url = new URL(window.location.href);
    if (!url.searchParams.has("focus")) return;
    url.searchParams.delete("focus");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);

  useEffect(() => {
    if (!focusId || !listSettled) return;
    // 等新列表完成布局后再定位
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(`conference-${focusId}`);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        focusRelaxed.current = false;
        setHighlightId(focusId);
        setFocusId(null);
      } else if (!focusRelaxed.current) {
        focusRelaxed.current = true;
        setFilters({ ...EMPTY_CONFERENCE_FILTERS, includeClosed: true });
      } else {
        focusRelaxed.current = false;
        setFocusId(null);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusId, listSettled, data]);

  useEffect(() => {
    if (!highlightId) return;
    const timer = window.setTimeout(() => setHighlightId(null), 2000);
    return () => window.clearTimeout(timer);
  }, [highlightId]);

  const focusConference = (conference: ConferenceDeadlineDto) => {
    focusRelaxed.current = false;
    setFocusId(conference.id);
  };

  const resetFilters = () =>
    setFilters((prev) => ({
      ...EMPTY_CONFERENCE_FILTERS,
      includeClosed: prev.includeClosed,
      followedOnly: prev.followedOnly,
    }));

  return (
    <div className="flex flex-col gap-5">
      <FollowedConferences items={followed.items} now={now} onSelect={focusConference} />

      <ConferenceFilterBar
        filters={{ ...filters, followedOnly }}
        canFilterFollowed={Boolean(followed.userId)}
        categories={categories.data?.items}
        total={data?.total}
        fetching={deadlines.isFetching && !deadlines.isPending}
        onChange={setFilters}
        onReset={resetFilters}
      />

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
      ) : (
        <div className="relative flex flex-col gap-5">
          {/* popLayout：移除的卡片脱离文档流淡出，其余卡片同时平滑补位 */}
          <AnimatePresence mode="popLayout">
            {data?.items.map((conference, index) => (
              <ConferenceCard
                key={conference.id}
                conference={conference}
                categoryName={categoryNames.get(conference.category)}
                // Closed / TBD cannot change as time moves forward: freeze their clock.
                now={conference.status === "open" ? now : deadlines.dataUpdatedAt}
                index={index}
                following={followed.ids.has(conference.id)}
                followResolving={followed.isResolving}
                highlighted={highlightId === conference.id}
              />
            ))}
            {data && data.items.length === 0 && (
              <motion.div
                key="empty"
                layout="position"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card"
              >
                {followedOnly
                  ? `还没有${filters.includeClosed ? "" : "未截止的"}关注会议，点击卡片上的「关注截稿」即可添加`
                  : `暂无符合条件的${filters.includeClosed ? "" : "未截止"}会议`}
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
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
