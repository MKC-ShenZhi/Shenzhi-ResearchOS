"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiJson, ApiError } from "@/clients/backend/http";
import type { KnowledgePaperHit, ReadingHistoryResponse } from "@/clients/knowledge";
import { KnowledgeResultCard } from "@/features/knowledge/search/components/result-card";

const MAX_PAGE = 5;

export function ReadingHistory() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ReadingHistoryResponse["items"]>([]);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [unauthenticated, setUnauthenticated] = useState(false);
  const loadingMore = useRef(false);
  const sentinel = useRef<HTMLDivElement>(null);

  const loadPage = useCallback(async (nextPage: number, replace: boolean) => {
    if (loadingMore.current || nextPage > MAX_PAGE) return;
    loadingMore.current = true;
    setPending(true);
    setError(null);
    try {
      const response = await apiJson<ReadingHistoryResponse>(
        `/history?page=${nextPage}&page_size=20&query=${encodeURIComponent(query.trim())}`,
      );
      setItems((current) => replace ? response.items : [...current, ...response.items]);
      setPage(response.page);
      setTotal(response.total);
      setUnauthenticated(false);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setUnauthenticated(true);
      else setError(reason);
    } finally {
      loadingMore.current = false;
      setPending(false);
    }
  }, [query]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPage(1, true), 250);
    return () => window.clearTimeout(timer);
  }, [loadPage, query]);

  useEffect(() => {
    const target = sentinel.current;
    if (!target) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && page > 0 && items.length < total) void loadPage(page + 1, false);
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [items.length, loadPage, page, total]);

  const asHit = (item: ReadingHistoryResponse["items"][number]): KnowledgePaperHit => ({
    ...item,
    id: item.paper_id,
    score: null,
    rank: null,
  });

  return (
    <section className="min-w-0 flex-1 p-8">
      <div>
        <h1 className="text-xl font-bold text-ink">浏览历史</h1>
        <p className="mt-1 text-xs text-faint">按最近浏览时间排列</p>
      </div>
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="搜索论文的标题/作者/会议"
        className="mt-5 h-10 w-full max-w-[460px] rounded-xl border border-line bg-card px-4 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
      />

      {unauthenticated ? (
        <div className="mt-8 rounded-2xl bg-card p-12 text-center text-sm text-muted shadow-card">该功能需要登录后使用，请先登录</div>
      ) : error ? (
        <div className="mt-8 rounded-2xl bg-card p-12 text-center text-sm text-muted shadow-card">
          <p>浏览历史加载失败，请稍后重试</p>
          <button type="button" onClick={() => void loadPage(1, true)} className="mt-3 text-primary">重试</button>
        </div>
      ) : !pending && items.length === 0 ? (
        <div className="mt-8 rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">
          {query.trim() ? "未找到匹配的论文" : "暂无浏览记录"}
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          {items.map((item, index) => (
            <KnowledgeResultCard
              key={`${item.paper_id}-${item.last_viewed_at}`}
              hit={asHit(item)}
              index={index}
              returnTo="/knowledge/papers"
              historyMode
              lastViewedAt={item.last_viewed_at}
            />
          ))}
          <div ref={sentinel} className="h-1" />
          {pending && <p className="py-4 text-center text-xs text-faint">正在加载…</p>}
          {!pending && page >= MAX_PAGE && items.length >= total && <p className="py-4 text-center text-xs text-faint">没有更多浏览记录</p>}
        </div>
      )}
    </section>
  );
}