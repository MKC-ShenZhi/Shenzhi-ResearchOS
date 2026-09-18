import { PenSquare } from "lucide-react";
import { drPlan } from "@/features/deep-research/data";
import { cn } from "@/lib/utils";
import type { DRSectionState } from "./use-deep-research-run";

const DOT: Record<DRSectionState, string> = {
  todo: "bg-faint/50",
  running: "animate-pulse bg-primary",
  done: "bg-success",
};

/** 研究计划卡 —— 大纲节状态由运行事件流派生(「编辑」为原型展示,无行为) */
export function PlanCard({
  sectionState,
}: {
  sectionState: Record<string, DRSectionState>;
}) {
  return (
    <section className="rounded-2xl bg-card p-4 shadow-card">
      <div className="flex items-center">
        <h2 className="text-sm font-semibold text-ink">研究计划</h2>
        <button
          type="button"
          title="原型阶段仅展示"
          aria-disabled="true"
          className="ml-auto flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-faint transition-colors hover:bg-chip hover:text-muted"
        >
          <PenSquare className="size-3" />
          编辑
        </button>
      </div>
      <ol className="mt-3 space-y-2.5">
        {drPlan.map((sec) => {
          const state = sectionState[sec.id] ?? "todo";
          return (
            <li key={sec.id} className="flex items-start gap-2.5">
              <span
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  DOT[state],
                )}
              />
              <div className="min-w-0">
                <p
                  className={cn(
                    "text-[13px] leading-snug",
                    state === "todo" ? "text-faint" : "text-ink",
                  )}
                >
                  {sec.title}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-faint">
                  {sec.query}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
