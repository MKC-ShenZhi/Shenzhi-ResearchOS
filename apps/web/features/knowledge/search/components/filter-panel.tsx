"use client";

import { useMemo, useState } from "react";
import { Filter, Plus, SlidersHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { KnowledgeFilters } from "../search-url-state";

export type { KnowledgeFilters } from "../search-url-state";

const EMPTY: KnowledgeFilters = {
  yearFrom: null,
  yearTo: null,
  venue: [],
  author: [],
  keyword: [],
  subject: [],
};

function hasFilters(filters: KnowledgeFilters): boolean {
  return (
    filters.yearFrom !== null ||
    filters.yearTo !== null ||
    filters.venue.length > 0 ||
    filters.author.length > 0 ||
    filters.keyword.length > 0 ||
    filters.subject.length > 0
  );
}

/** 单选标签输入（回车/添加按钮加入，chip 可移除） */
function TagInput({
  label,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const text = draft.trim();
    if (!text || value.includes(text)) return;
    onChange([...value, text]);
    setDraft("");
  };

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-ink-2">{label}</p>
      <div className="flex gap-1.5">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          className="h-8 text-xs"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 shrink-0 px-2"
          onClick={add}
          disabled={disabled || !draft.trim()}
          aria-label={`添加${label}`}
        >
          <Plus className="size-3.5" />
        </Button>
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((item) => (
            <span
              key={item}
              className="inline-flex items-center gap-1 rounded-md bg-primary-soft px-2 py-0.5 text-[11px] text-primary"
            >
              {item}
              <button
                type="button"
                onClick={() => onChange(value.filter((v) => v !== item))}
                className="rounded-sm hover:text-primary-deep"
                aria-label={`移除 ${item}`}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** 论文检索筛选面板 */
export function KnowledgeFilterPanel({
  filters,
  onChange,
  disabled,
}: {
  filters: KnowledgeFilters;
  onChange: (filters: KnowledgeFilters) => void;
  disabled?: boolean;
}) {
  const activeCount = useMemo(
    () =>
      (filters.yearFrom !== null ? 1 : 0) +
      (filters.yearTo !== null ? 1 : 0) +
      filters.venue.length +
      filters.author.length +
      filters.keyword.length +
      filters.subject.length,
    [filters],
  );

  const set = <K extends keyof KnowledgeFilters>(key: K, value: KnowledgeFilters[K]) =>
    onChange({ ...filters, [key]: value });

  return (
    <div className="rounded-2xl border border-line bg-card p-4 shadow-card">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink">
          <SlidersHorizontal className="size-4 text-primary" />
          筛选
          {activeCount > 0 && (
            <span className="rounded-full bg-primary-soft px-1.5 py-0.5 text-[10px] font-medium text-primary">
              {activeCount}
            </span>
          )}
        </p>
        {hasFilters(filters) && (
          <button
            type="button"
            onClick={() => onChange({ ...EMPTY })}
            className="text-[11px] text-muted transition-colors hover:text-danger"
          >
            清除全部
          </button>
        )}
      </div>

      <div className="mt-4 space-y-4">
        {/* 年份区间 */}
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-ink-2">年份区间</p>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              value={filters.yearFrom ?? ""}
              onChange={(event) =>
                set("yearFrom", event.target.value ? Number(event.target.value) : null)
              }
              placeholder="起始"
              disabled={disabled}
              className="h-8 text-xs"
            />
            <span className="text-faint">–</span>
            <Input
              type="number"
              value={filters.yearTo ?? ""}
              onChange={(event) =>
                set("yearTo", event.target.value ? Number(event.target.value) : null)
              }
              placeholder="结束"
              disabled={disabled}
              className="h-8 text-xs"
            />
          </div>
        </div>

        <TagInput
          label="会议"
          value={filters.venue}
          onChange={(next) => set("venue", next)}
          placeholder="如 RSS / ICRA"
          disabled={disabled}
        />
        <TagInput
          label="作者"
          value={filters.author}
          onChange={(next) => set("author", next)}
          placeholder="如 Cheng Chi"
          disabled={disabled}
        />
        <TagInput
          label="关键词"
          value={filters.keyword}
          onChange={(next) => set("keyword", next)}
          placeholder="如 Diffusion Policy"
          disabled={disabled}
        />
        <TagInput
          label="学科"
          value={filters.subject}
          onChange={(next) => set("subject", next)}
          placeholder="如 Robotics"
          disabled={disabled}
        />
      </div>

      {disabled && (
        <p className="mt-4 flex items-center gap-1.5 rounded-lg bg-panel px-2.5 py-2 text-[11px] text-faint">
          <Filter className="size-3" />
          请先输入关键词开始检索
        </p>
      )}
    </div>
  );
}
