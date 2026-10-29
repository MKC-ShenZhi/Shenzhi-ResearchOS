"use client";

import { Check, Medal, RotateCcw, Tag } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConferenceCategoryDto } from "@/clients/backend/conferences";
import {
  RANK_CHIPS,
  hasActiveFilters,
  isRankChipActive,
  toggleCategory,
  toggleRankChip,
  type ConferenceFilterState,
} from "@/features/submit/services/conference-filters";

interface ConferenceFilterPanelProps {
  filters: ConferenceFilterState;
  categories: ConferenceCategoryDto[] | undefined;
  onChange: (next: ConferenceFilterState) => void;
  onReset: () => void;
}

/** 左侧筛选面板 —— 等级 chips（同一体系内为“或”，跨体系为“且”）+ CCF 研究方向 */
export function ConferenceFilterPanel({ filters, categories, onChange, onReset }: ConferenceFilterPanelProps) {
  return (
    <aside className="rounded-2xl bg-card p-5 shadow-card">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Medal className="size-4 text-muted" />
          <h2 className="text-[15px] font-semibold text-ink">等级筛选</h2>
        </div>
        {hasActiveFilters(filters) && (
          <button
            type="button"
            onClick={onReset}
            className="flex cursor-pointer items-center gap-1 text-xs text-muted hover:text-primary"
          >
            <RotateCcw className="size-3" />
            重置
          </button>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        {RANK_CHIPS.map((chip) => {
          const active = isRankChipActive(filters, chip);
          return (
            <button
              key={chip.label}
              type="button"
              onClick={() => onChange(toggleRankChip(filters, chip))}
              aria-pressed={active}
              className={cn(
                "h-9 cursor-pointer rounded-full border text-[13px] transition-colors",
                active
                  ? "border-primary bg-primary-soft font-medium text-primary"
                  : "border-line bg-panel text-ink-2 hover:border-primary/40",
              )}
            >
              {chip.label}
            </button>
          );
        })}
      </div>

      <div className="mt-6 flex items-center gap-2">
        <Tag className="size-4 text-muted" />
        <h2 className="text-[15px] font-semibold text-ink">研究方向</h2>
      </div>

      <ul className="mt-3">
        {(categories ?? []).map((category) => {
          const active = filters.categories.includes(category.id);
          return (
            <li key={category.id}>
              <button
                type="button"
                role="checkbox"
                aria-checked={active}
                onClick={() => onChange(toggleCategory(filters, category.id))}
                className="group flex w-full cursor-pointer items-start gap-3 py-2.5 text-left"
              >
                <span
                  className={cn(
                    "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-line bg-card group-hover:border-primary/50",
                  )}
                >
                  {active && <Check className="size-3" strokeWidth={3} />}
                </span>
                <span className="flex-1 text-[13px] leading-snug text-ink-2">{category.name}</span>
                <span className="text-xs text-faint">{category.count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
