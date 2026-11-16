"use client";

import { ChevronRight, Medal, Tag } from "lucide-react";
import { DIRECTION_ROWS, LEVEL_CHIPS } from "@/features/submit/data";
import { cn } from "@/lib/utils";

interface FilterPanelProps {
  activeLevels: string[];
  onToggleLevel: (chip: string) => void;
}

/** 左侧筛选面板 —— 等级筛选 chips + 研究方向复选(对应投稿页 SVG 左栏) */
export function FilterPanel({ activeLevels, onToggleLevel }: FilterPanelProps) {
  return (
    <aside className="rounded-2xl bg-card p-5 shadow-card">
      <div className="flex items-center gap-2">
        <Medal className="size-4 text-muted" />
        <h2 className="text-[15px] font-semibold text-ink">等级筛选</h2>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        {LEVEL_CHIPS.map((chip) => {
          const active = activeLevels.includes(chip);
          return (
            <button
              key={chip}
              type="button"
              onClick={() => onToggleLevel(chip)}
              aria-pressed={active}
              className={cn(
                "h-9 cursor-pointer rounded-full border text-[13px] transition-colors",
                active
                  ? "border-primary bg-primary-soft font-medium text-primary"
                  : "border-line bg-panel text-ink-2 hover:border-primary/40",
              )}
            >
              {chip}
            </button>
          );
        })}
      </div>

      <div className="mt-6 flex items-center gap-2">
        <Tag className="size-4 text-muted" />
        <h2 className="text-[15px] font-semibold text-ink">研究方向</h2>
      </div>

      <ul className="mt-3">
        {DIRECTION_ROWS.map((row) => (
          <li
            key={row.lines.join("")}
            className="group flex cursor-pointer items-start gap-3 py-2.5"
          >
            <span className="mt-0.5 size-4 shrink-0 rounded border border-line bg-card transition-colors group-hover:border-primary/50" />
            <span className="flex-1 text-[13px] leading-snug text-ink-2">
              {row.lines.map((line, i) => (
                <span key={i} className="block">
                  {line}
                </span>
              ))}
            </span>
            <span className="text-xs text-faint">{row.count}</span>
            <ChevronRight className="size-3.5 text-faint" />
          </li>
        ))}
      </ul>
    </aside>
  );
}
