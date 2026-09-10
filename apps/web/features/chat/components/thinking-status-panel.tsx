"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  ChevronDown,
  ChevronRight,
  Sparkles,
  Timer,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { KnowledgeGroundingState } from "@/types/ai-search";

/** Agent B 风格：阶段 / 来源数 / 耗时 / 截断与附件告警 */
export function ThinkingStatusPanel({
  thought,
  readCount,
  durationMs,
  warnings = [],
  streaming,
  knowledgeGrounding,
}: {
  thought: string;
  readCount?: number;
  durationMs?: number;
  warnings?: string[];
  streaming?: boolean;
  knowledgeGrounding?: KnowledgeGroundingState;
}) {
  const [open, setOpen] = useState(false);
  const degraded = knowledgeGrounding === "unavailable" || knowledgeGrounding === "unverified";
  const effectiveReadCount = degraded ? undefined : readCount;
  const items = useMemo(() => {
    const rows: { icon: typeof Sparkles; label: string; value: string; tone?: "danger" }[] = [];
    if (thought) rows.push({ icon: Sparkles, label: "阶段", value: thought });
    if (typeof effectiveReadCount === "number") {
      rows.push({
        icon: BookOpenCheck,
        label: "已阅读",
        value: effectiveReadCount === 0 ? "检索中…" : `${effectiveReadCount} 项来源`,
      });
    }
    if (typeof durationMs === "number" && durationMs > 0) {
      rows.push({
        icon: Timer,
        label: "耗时",
        value: `${(durationMs / 1000).toFixed(1)}s`,
      });
    }
    (warnings ?? []).forEach((warning) => {
      rows.push({ icon: AlertTriangle, label: "告警", value: warning, tone: "danger" });
    });
    return rows;
  }, [thought, effectiveReadCount, durationMs, warnings]);

  if (!items.length && !streaming) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-line/60 bg-sidebar/60">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left"
      >
        {open ? <ChevronDown className="size-3.5 text-faint" /> : <ChevronRight className="size-3.5 text-faint" />}
        <Sparkles className={cn("size-3.5", streaming ? "animate-pulse text-primary" : "text-muted")} />
        <span className="text-[12px] font-medium text-ink-2">
          {streaming
            ? "思考中…"
            : knowledgeGrounding === "unavailable"
              ? "知识检索未生效"
              : knowledgeGrounding === "unverified"
                ? "未形成可验证引用"
                : "思考完成"}
        </span>
      </button>
      {open && (
        <div className="space-y-1 border-t border-line/40 px-3 py-2">
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <div key={`${item.label}-${item.value}`} className="flex items-start gap-2 text-[12px]">
                <Icon className={cn("mt-0.5 size-3.5 shrink-0", item.tone === "danger" ? "text-amber-600" : "text-faint")} />
                <span className="text-faint">{item.label}</span>
                <span className={cn("min-w-0 flex-1 text-ink-2", item.tone === "danger" && "text-amber-800 dark:text-amber-200")}>
                  {item.value}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
