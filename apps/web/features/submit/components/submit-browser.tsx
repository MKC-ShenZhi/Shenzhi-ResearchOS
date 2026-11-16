"use client";

import { useState } from "react";
import { FilterPanel } from "./filter-panel";
import { VenueCard } from "./venue-card";
import { venues } from "@/features/submit/data";
import { cn } from "@/lib/utils";

const TABS = ["截止日期", "Rebuttal", "录用通知", "最终定稿", "会议时间"];

/** 等级 chip → 徽章名映射(用于过滤) */
const LEVEL_TO_BADGE: Record<string, string> = {
  "CCF-A": "CCF A",
  "CCF-C": "CCF C",
  "CAAI-A": "CAAI A",
  "CAAI-C": "CAAI C",
  "CORE-A*": "CORE A*",
  "TH-CPL A": "TH-CPL A",
  "TH-CPL B": "TH-CPL B",
  中科院1区: "中科院1区",
};

/** 投稿浏览区 —— 标签切换 + 等级过滤(原型热区 → React 状态驱动),按会议/期刊分类展示 */
export function SubmitBrowser({ kind }: { kind: "conference" | "journal" }) {
  const [tab, setTab] = useState(TABS[0]);
  const [levels, setLevels] = useState<string[]>([]);

  const toggleLevel = (chip: string) =>
    setLevels((prev) =>
      prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip],
    );

  const base = venues.filter((v) => v.kind === kind);
  const filtered =
    levels.length === 0
      ? base
      : base.filter((v) =>
          levels.some((chip) => {
            const badge = LEVEL_TO_BADGE[chip];
            return badge && v.badges.includes(badge as never);
          }),
        );

  return (
    <>
      <div className="flex items-center justify-between">
        <div className="flex rounded-full bg-sidebar p-1">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "h-8 cursor-pointer rounded-full px-4 text-[13px] transition-colors",
                tab === t
                  ? "bg-primary font-medium text-white"
                  : "text-muted hover:text-ink-2",
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <span className="text-sm text-faint">
          {levels.length === 0 ? base.length : filtered.length} 条结果
        </span>
      </div>

      <div className="mt-5 grid items-start gap-6 xl:grid-cols-[300px_1fr]">
        <FilterPanel activeLevels={levels} onToggleLevel={toggleLevel} />
        <div className="space-y-6">
          {filtered.map((venue, i) => (
            <VenueCard key={venue.id} venue={venue} index={i} />
          ))}
          {filtered.length === 0 && (
            <div className="rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">
              暂无符合筛选条件的{kind === "conference" ? "会议" : "期刊"}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
