"use client";

import { useEffect } from "react";
import { ShieldAlert, User, Zap } from "lucide-react";
import type { Checkpoint, CheckpointOption } from "@/features/auto-research/research-run";
import { cn } from "@/lib/utils";

interface CheckpointCardProps {
  checkpoint: Checkpoint;
  /** SLIM 呈现(自动模式下的非关键关卡) */
  slim: boolean;
  /** 自动模式下 SLIM 卡的自动继续倒计时秒数;0 = 不自动继续 */
  autoContinueAfter?: number;
  /** auto = 倒计时触发的自动继续(日志需如实记录) */
  onResolve: (option: CheckpointOption, auto?: boolean) => void;
}

const METRIC_STATE = {
  ok: "text-success",
  warn: "text-[#d97706]",
  bad: "text-danger",
} as const;

/** 关卡决策卡 —— FULL / SLIM 两档;MANDATORY 永不 SLIM */
export function CheckpointCard({
  checkpoint,
  slim,
  autoContinueAfter = 0,
  onResolve,
}: CheckpointCardProps) {
  const mandatory = checkpoint.level === "mandatory";

  useEffect(() => {
    if (!slim || autoContinueAfter <= 0) return;
    const timer = setTimeout(
      () => onResolve(checkpoint.options[0], true),
      autoContinueAfter * 1000,
    );
    return () => clearTimeout(timer);
  }, [slim, autoContinueAfter, checkpoint, onResolve]);

  if (slim) {
    return (
      <div className="mb-3 flex items-center gap-3 rounded-xl border border-line bg-panel px-3 py-2">
        <Zap className="size-4 shrink-0 text-primary" />
        <p className="min-w-0 flex-1 truncate text-xs text-ink-2">
          {checkpoint.title}
          <span className="ml-2 text-faint">{autoContinueAfter > 0 ? `${autoContinueAfter}s 后自动继续` : ""}</span>
        </p>
        <button
          type="button"
          className="shrink-0 cursor-pointer rounded-lg bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
          onClick={() => onResolve(checkpoint.options[0])}
        >
          继续
        </button>
        <button
          type="button"
          className="shrink-0 cursor-pointer rounded-lg border border-line px-3 py-1 text-xs text-muted"
          onClick={() => onResolve({ label: "暂停", action: "end" })}
        >
          暂停
        </button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "mb-3 rounded-xl border-2 bg-card p-4 shadow-pop",
        mandatory ? "border-[#d97706]" : "border-primary",
      )}
    >
      <div className="flex items-center gap-2">
        {mandatory ? (
          <ShieldAlert className="size-4 text-[#d97706]" />
        ) : (
          <User className="size-4 text-primary" />
        )}
        <p className="text-sm font-semibold text-ink">{checkpoint.title}</p>
        <span
          className={cn(
            "ml-auto shrink-0 rounded-md px-2 py-0.5 text-[10px] font-medium",
            mandatory ? "bg-[#d97706]/10 text-[#d97706]" : "bg-primary-soft text-primary",
          )}
        >
          {mandatory ? "MANDATORY · 不可跳过" : "决策关卡"}
        </span>
      </div>

      {checkpoint.metrics && (
        <div className="mt-3 grid grid-cols-3 gap-2">
          {checkpoint.metrics.map((m) => (
            <div key={m.label} className="rounded-lg bg-panel px-2.5 py-2">
              <p className="text-[10px] text-faint">{m.label}</p>
              <p className={cn("mt-0.5 text-xs font-semibold", m.state ? METRIC_STATE[m.state] : "text-ink")}>
                {m.value}
              </p>
            </div>
          ))}
        </div>
      )}

      {checkpoint.deliverables && (
        <p className="mt-2.5 text-[11px] text-muted">
          交付物:{checkpoint.deliverables.join(" · ")}
        </p>
      )}

      {checkpoint.flagged && checkpoint.flagged.length > 0 && (
        <div className="mt-2 rounded-lg bg-[#d97706]/8 px-2.5 py-2">
          {checkpoint.flagged.map((f) => (
            <p key={f} className="text-[11px] leading-5 text-[#d97706]">
              ⚠ {f}
            </p>
          ))}
        </div>
      )}

      <p className="mt-3 text-xs leading-5 text-ink-2">{checkpoint.question}</p>

      <div className="mt-3 flex flex-wrap gap-2">
        {checkpoint.options.map((opt) => (
          <button
            key={opt.label}
            type="button"
            title={opt.hint}
            onClick={() => onResolve(opt)}
            className={cn(
              "cursor-pointer rounded-xl px-3.5 py-1.5 text-xs font-medium transition-colors",
              opt.tone === "primary" && "bg-primary text-primary-foreground hover:opacity-90",
              opt.tone === "danger" && "bg-danger-soft text-danger hover:opacity-80",
              (!opt.tone || opt.tone === "ghost") && "border border-line text-ink-2 hover:bg-panel",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
