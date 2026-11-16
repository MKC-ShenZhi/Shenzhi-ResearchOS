"use client";

import { useState } from "react";
import {
  ArrowLeft,
  Download,
  PanelLeftClose,
  PanelLeftOpen,
  Share2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { FollowUpInput } from "@/components/common/composer/follow-up-input";
import { cn } from "@/lib/utils";
import { PlanCard } from "./plan-card";
import { ReportViewer } from "./report-viewer";
import { SourceWall } from "./source-wall";
import { StepTimeline } from "./step-timeline";
import { useDeepResearchRun } from "./use-deep-research-run";

/** 耗时格式化:m:ss */
function fmtElapsed(ms: number) {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Deep Research Session 工作台 —— 顶条 + 左栏(过程)/ 右栏(报告)双栏 */
export function ResearchWorkbench({
  question,
  instant,
  onBack,
}: {
  question: string;
  instant: boolean;
  onBack: () => void;
}) {
  const run = useDeepResearchRun(instant);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="mx-auto max-w-[1280px] px-6 py-5">
      {/* 顶条:返回 / 问题 / 状态 / 耗时 / 导出分享 */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          aria-label="返回研究列表"
          title="返回研究列表"
          className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-card hover:text-ink"
        >
          <ArrowLeft className="size-4" />
        </button>
        <p className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
          {question}
        </p>
        <span
          className={cn(
            "shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium",
            run.phase === "done"
              ? "bg-success-soft text-success"
              : "bg-primary-soft text-primary",
          )}
        >
          {run.phase === "done" ? "已完成" : "研究中"}
        </span>
        <span className="shrink-0 text-xs text-faint">
          {fmtElapsed(run.elapsedMs)}
        </span>
        <div className="ml-2 flex shrink-0 gap-2">
          <Button
            variant="outline"
            size="sm"
            className="rounded-lg"
            title="原型阶段仅展示"
          >
            <Download className="size-3.5" />
            导出
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-lg"
            title="原型阶段仅展示"
          >
            <Share2 className="size-3.5" />
            分享
          </Button>
        </div>
      </div>

      {/* 双栏:左过程 / 右报告 */}
      <div className="mt-5 flex items-start gap-5">
        {collapsed ? (
          <div className="w-12 shrink-0">
            <button
              type="button"
              onClick={() => setCollapsed(false)}
              aria-label="展开研究过程"
              title="展开研究过程"
              aria-expanded={false}
              className="flex size-12 cursor-pointer items-center justify-center rounded-2xl bg-card text-muted shadow-card transition-colors hover:text-ink"
            >
              <PanelLeftOpen className="size-[18px]" strokeWidth={1.8} />
            </button>
          </div>
        ) : (
          <aside className="w-[340px] shrink-0 space-y-4">
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setCollapsed(true)}
                aria-label="收起研究过程"
                title="收起研究过程"
                aria-expanded={true}
                className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-faint transition-colors hover:bg-card hover:text-muted"
              >
                <PanelLeftClose className="size-4" strokeWidth={1.8} />
              </button>
            </div>
            <PlanCard sectionState={run.sectionState} />
            <StepTimeline events={run.visibleEvents} />
            <SourceWall count={run.visibleSources} />
          </aside>
        )}

        <div className="min-w-0 flex-1 space-y-5">
          <ReportViewer sectionState={run.sectionState} />
          <FollowUpInput />
        </div>
      </div>
    </div>
  );
}
