"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpDown, Network, Search, X } from "lucide-react";
import { getKnowledgeClient, KnowledgeClientError } from "@/clients/knowledge";
import type {
  KnowledgePaperHit,
  KnowledgeRelatedPaper,
  KnowledgeRelationDirection,
} from "@/clients/knowledge";
import {
  filterByDirection,
  type GraphDirectionFilter,
} from "../lib/graph-utils";
import { cn } from "@/lib/utils";

const DIRECTION_OPTIONS: Array<{ value: GraphDirectionFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "reference", label: "参考文献" },
  { value: "citation", label: "引用本文" },
];

const DIRECTION_BADGE: Record<KnowledgeRelationDirection, { label: string; className: string }> = {
  reference: { label: "参考文献", className: "bg-primary-soft text-primary" },
  citation: { label: "引用本文", className: "bg-success-soft text-success" },
  both: { label: "双向关联", className: "bg-brand-gold/20 text-ink" },
};

interface GraphRelatedPanelProps {
  centerTitle: string;
  related: KnowledgeRelatedPaper[];
  direction: GraphDirectionFilter;
  onDirectionChange: (direction: GraphDirectionFilter) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onPickCenter: (paperId: string) => void;
  loading?: boolean;
}

/** 左栏 —— 中心论文搜索 + 关联论文列表（References / Citations 方向筛选） */
export function GraphRelatedPanel({
  centerTitle,
  related,
  direction,
  onDirectionChange,
  selectedId,
  onSelect,
  onPickCenter,
  loading,
}: GraphRelatedPanelProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<KnowledgePaperHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<KnowledgeClientError | null>(null);
  const [open, setOpen] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sequence = useRef(0);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const text = query.trim();
    const current = ++sequence.current;
    timer.current = setTimeout(() => {
      if (!text) {
        setSuggestions([]);
        setSearchError(null);
        setOpen(false);
        setSearching(false);
        return;
      }
      setSearchError(null);
      setSearching(true);
      getKnowledgeClient()
        .search({ query: text, topK: 8, yearFrom: null, yearTo: null, venue: [], author: [], keyword: [], subject: [] })
        .then((data) => {
          if (current !== sequence.current) return;
          setSuggestions(data.results.slice(0, 8));
          setSearchError(null);
          setOpen(true);
        })
        .catch((error: unknown) => {
          if (current !== sequence.current) return;
          setSuggestions([]);
          setSearchError(
            error instanceof KnowledgeClientError
              ? error
              : new KnowledgeClientError("UNKNOWN", "中心论文搜索失败"),
          );
        })
        .finally(() => {
          if (current === sequence.current) setSearching(false);
        });
    }, 280);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [query, retryNonce]);

  const visible = filterByDirection(related, direction);
  const counts: Record<GraphDirectionFilter, number> = {
    all: related.length,
    reference: filterByDirection(related, "reference").length,
    citation: filterByDirection(related, "citation").length,
    both: filterByDirection(related, "both").length,
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 中心论文搜索 */}
      <div className="relative shrink-0">
        <div className="flex items-center gap-2 rounded-xl border border-line bg-panel px-3">
          <Search className="size-4 shrink-0 text-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={() => suggestions.length > 0 && setOpen(true)}
            placeholder="搜索并切换中心论文…"
            className="h-9 min-w-0 flex-1 text-xs outline-none bg-transparent text-ink placeholder:text-faint"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="text-faint hover:text-muted"
              aria-label="清空搜索"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        {open && suggestions.length > 0 && (
          <div className="absolute inset-x-0 top-11 z-20 max-h-64 overflow-auto rounded-xl border border-line bg-card py-1 shadow-pop">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                onClick={() => {
                  onPickCenter(suggestion.id);
                  setQuery("");
                  setOpen(false);
                }}
                className="block w-full px-3 py-2 text-left transition-colors hover:bg-panel"
              >
                <p className="truncate text-xs font-medium text-ink">{suggestion.title}</p>
                <p className="mt-0.5 truncate text-[10px] text-faint">
                  {suggestion.authors.slice(0, 3).join(", ")} · {suggestion.year ?? "—"}
                </p>
              </button>
            ))}
          </div>
        )}
        {searching && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-faint">
            搜索中…
          </span>
        )}
        {searchError && !searching && (
          <div className="mt-2 flex items-center justify-between rounded-lg bg-danger-soft px-2.5 py-2 text-[11px] text-danger">
            <span className="truncate">中心论文搜索失败：{searchError.message}</span>
            <button
              type="button"
              className="ml-2 shrink-0 font-medium underline underline-offset-2"
              onClick={() => setRetryNonce((value) => value + 1)}
            >
              重试
            </button>
          </div>
        )}
      </div>

      {/* 中心论文卡 */}
      <div className="mt-3 shrink-0 rounded-xl border-l-2 border-primary bg-panel p-3">
        <p className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-primary">
          <Network className="size-3" />
          Origin paper
        </p>
        <p className="mt-1 line-clamp-2 text-[13px] font-semibold leading-snug text-ink">
          {centerTitle}
        </p>
      </div>

      {/* 方向筛选 */}
      <div className="mt-3 flex shrink-0 items-center gap-1">
        <ArrowUpDown className="mr-1 size-3.5 text-faint" />
        {DIRECTION_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onDirectionChange(option.value)}
            className={cn(
              "rounded-full px-2.5 py-1 text-[11px] transition-colors",
              direction === option.value
                ? "bg-primary text-primary-foreground"
                : "bg-chip text-muted hover:text-ink",
            )}
          >
            {option.label}
            <span className="ml-1 opacity-70">{counts[option.value]}</span>
          </button>
        ))}
      </div>

      {/* 关联论文列表 */}
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
        <p className="text-[11px] font-medium text-faint">关联论文 · {visible.length}</p>
        <ul className="mt-1.5 space-y-1">
          {visible.map((paper) => {
            const active = paper.id === selectedId;
            const badge = DIRECTION_BADGE[paper.relationDirection];
            return (
              <li key={paper.id}>
                <button
                  type="button"
                  onClick={() => onSelect(paper.id)}
                  className={cn(
                    "w-full rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-panel",
                    active && "bg-primary-soft hover:bg-primary-soft",
                  )}
                >
                  <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium", badge.className)}>
                    {badge.label}
                  </span>
                  <p className={cn("mt-1 text-[13px] font-medium leading-snug", active ? "text-primary" : "text-ink-2")}>
                    {paper.title}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-faint">
                    {paper.authors.slice(0, 2).join(", ") || "未知作者"} · {paper.year ?? "—"}
                    {paper.venue ? ` · ${paper.venue}` : ""}
                  </p>
                </button>
              </li>
            );
          })}
          {!loading && visible.length === 0 && (
            <li className="rounded-lg bg-panel/60 px-3 py-6 text-center text-xs text-faint">
              当前方向暂无关联论文
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
