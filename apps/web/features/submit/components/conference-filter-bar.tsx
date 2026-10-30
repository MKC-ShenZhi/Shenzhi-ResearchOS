"use client";

import { useCallback, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, Loader2, Medal, RotateCcw, Search, Tag, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { usePopoverPlacement } from "@/lib/use-popover-placement";
import type { ConferenceCategoryDto } from "@/clients/backend/conferences";
import {
  RANK_CHIPS,
  hasActiveFilters,
  isRankChipActive,
  toggleCategory,
  toggleRankChip,
  type RankSystem,
  type ConferenceFilterState,
} from "@/features/submit/services/conference-filters";
import { useDismiss } from "@/features/submit/hooks/use-dismiss";
import { PopoverPanel } from "./popover-panel";

const RANK_SYSTEM_LABELS: Record<RankSystem, string> = { ccf: "CCF", core: "CORE", thcpl: "TH-CPL" };

const RANK_GROUPS = (Object.keys(RANK_SYSTEM_LABELS) as RankSystem[]).map((system) => ({
  system,
  chips: RANK_CHIPS.filter((chip) => chip.system === system),
}));

/** 工具栏上的下拉筛选：触发按钮显示已选数量，内容在弹出面板中 */
function FilterPopover({
  icon: Icon,
  label,
  count,
  panelClassName,
  children,
}: {
  icon: typeof Medal;
  label: string;
  count: number;
  panelClassName?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const placement = usePopoverPlacement(open, rootRef, 360);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, rootRef, close);

  return (
    // 窄屏下弹层相对整个工具栏定位，避免从靠右的按钮展开时溢出屏幕
    <div ref={rootRef} className="static sm:relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "flex h-10 cursor-pointer items-center gap-1.5 rounded-xl border px-3.5 text-[13px] transition-colors",
          count > 0 || open
            ? "border-primary/40 bg-primary-soft text-primary"
            : "border-line bg-card text-ink-2 hover:border-primary/40",
        )}
      >
        <Icon className="size-4" />
        {label}
        <AnimatePresence initial={false}>
          {count > 0 && (
            <motion.span
              key="count"
              initial={{ opacity: 0, scale: 0.5, width: 0 }}
              animate={{ opacity: 1, scale: 1, width: "auto" }}
              exit={{ opacity: 0, scale: 0.5, width: 0 }}
              className="flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-primary px-1 text-[11px] font-medium text-primary-foreground"
            >
              {count}
            </motion.span>
          )}
        </AnimatePresence>
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      <PopoverPanel open={open} placement={placement} className={panelClassName}>
        {children}
      </PopoverPanel>
    </div>
  );
}

interface ConferenceFilterBarProps {
  filters: ConferenceFilterState;
  categories: ConferenceCategoryDto[] | undefined;
  total: number | undefined;
  fetching: boolean;
  onChange: (next: ConferenceFilterState) => void;
  onReset: () => void;
}

/**
 * 顶部筛选工具栏 —— 搜索 + 等级 / 研究方向下拉（同一体系内为“或”，跨体系为“且”），
 * 已选条件以可移除的标签展示，替代原左侧筛选栏，把横向空间让给会议卡片。
 */
export function ConferenceFilterBar({
  filters,
  categories,
  total,
  fetching,
  onChange,
  onReset,
}: ConferenceFilterBarProps) {
  const rankCount = filters.ccf.length + filters.core.length + filters.thcpl.length;
  const categoryNames = new Map((categories ?? []).map((category) => [category.id, category.name]));
  const activeTags = [
    ...RANK_CHIPS.filter((chip) => isRankChipActive(filters, chip)).map((chip) => ({
      key: `rank-${chip.label}`,
      label: chip.label,
      remove: () => onChange(toggleRankChip(filters, chip)),
    })),
    ...filters.categories.map((id) => ({
      key: `category-${id}`,
      label: categoryNames.get(id) ?? id,
      remove: () => onChange(toggleCategory(filters, id)),
    })),
  ];

  return (
    <div className="relative z-20 rounded-2xl border border-line/60 bg-card/90 p-3 shadow-card backdrop-blur-md lg:sticky lg:top-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <Input
            value={filters.q}
            onChange={(event) => onChange({ ...filters, q: event.target.value })}
            placeholder="搜索会议简称、全称，如 NeurIPS、Computer Vision"
            maxLength={100}
            aria-label="搜索会议"
            className="pl-10"
          />
        </div>

        <FilterPopover icon={Medal} label="等级" count={rankCount} panelClassName="w-72 p-3">
          <div className="flex flex-col gap-3">
            {RANK_GROUPS.map(({ system, chips }) => (
              <div key={system} className="flex items-center gap-3">
                <span className="w-12 shrink-0 text-xs font-medium text-muted">{RANK_SYSTEM_LABELS[system]}</span>
                <div className="flex flex-wrap gap-1.5">
                  {chips.map((chip) => {
                    const active = isRankChipActive(filters, chip);
                    return (
                      <button
                        key={chip.label}
                        type="button"
                        aria-pressed={active}
                        aria-label={chip.label}
                        onClick={() => onChange(toggleRankChip(filters, chip))}
                        className={cn(
                          "h-8 min-w-10 cursor-pointer rounded-full border px-3 text-[13px] transition-colors",
                          active
                            ? "border-primary bg-primary-soft font-medium text-primary"
                            : "border-line bg-panel text-ink-2 hover:border-primary/40",
                        )}
                      >
                        {chip.value}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
            <p className="border-t border-line pt-2.5 text-xs leading-relaxed text-faint">
              同一体系内满足任一即可，跨体系需同时满足
            </p>
          </div>
        </FilterPopover>

        <FilterPopover icon={Tag} label="研究方向" count={filters.categories.length} panelClassName="w-80">
          <ul className="max-h-[min(60vh,420px)] overflow-y-auto">
            {(categories ?? []).map((category) => {
              const active = filters.categories.includes(category.id);
              return (
                <li key={category.id}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={active}
                    onClick={() => onChange(toggleCategory(filters, category.id))}
                    className="group flex w-full cursor-pointer items-start gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-chip"
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
        </FilterPopover>

        <button
          type="button"
          aria-pressed={filters.includeClosed}
          onClick={() => onChange({ ...filters, includeClosed: !filters.includeClosed })}
          className={cn(
            "h-10 cursor-pointer rounded-xl border px-3.5 text-[13px] transition-colors",
            filters.includeClosed
              ? "border-primary bg-primary font-medium text-white"
              : "border-line bg-card text-ink-2 hover:border-primary/40",
          )}
        >
          显示已截止
        </button>

        <span className="ml-auto flex min-w-[88px] items-center justify-end gap-1.5 pr-1 text-sm text-faint" aria-live="polite">
          {fetching && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
          {total !== undefined && (
            <>
              <motion.span key={total} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}>
                {total}
              </motion.span>
              个会议
            </>
          )}
        </span>
      </div>

      <AnimatePresence initial={false}>
        {hasActiveFilters(filters) && (
          <motion.div
            key="active-tags"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="flex flex-wrap items-center gap-1.5 pt-2.5">
              <AnimatePresence initial={false} mode="popLayout">
                {activeTags.map((tag) => (
                  <motion.button
                    key={tag.key}
                    layout
                    type="button"
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ duration: 0.15 }}
                    onClick={tag.remove}
                    aria-label={`移除筛选：${tag.label}`}
                    className="flex h-7 cursor-pointer items-center gap-1 rounded-full bg-primary-soft pl-2.5 pr-2 text-xs text-primary transition-colors hover:bg-primary-soft/70"
                  >
                    {tag.label}
                    <X className="size-3" />
                  </motion.button>
                ))}
              </AnimatePresence>
              <motion.button
                layout
                type="button"
                onClick={onReset}
                className="flex h-7 cursor-pointer items-center gap-1 rounded-full px-2 text-xs text-muted transition-colors hover:text-primary"
              >
                <RotateCcw className="size-3" />
                清除全部
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
