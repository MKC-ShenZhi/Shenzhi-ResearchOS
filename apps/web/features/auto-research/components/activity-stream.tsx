"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { NODE_MAP } from "@/features/auto-research/research-pipeline";
import type { LogLine, LogLevel } from "@/features/auto-research/research-run";
import { cn } from "@/lib/utils";

const LEVEL_STYLE: Record<LogLevel, { dot: string; label: string }> = {
  info: { dot: "bg-faint", label: "text-muted" },
  decision: { dot: "bg-brand-violet", label: "text-brand-violet" },
  warn: { dot: "bg-[#d97706]", label: "text-[#d97706]" },
  error: { dot: "bg-danger", label: "text-danger" },
};

/** 动作流 —— Deli 日志协议产品化;decision 行可展开看决策理由 */
export function ActivityStream({ logs }: { logs: LogLine[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  if (logs.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-xs text-faint">
        点击「开始运行」,agent 的每一步动作都会出现在这里
      </div>
    );
  }

  return (
    <div className="scrollbar-subtle h-72 space-y-1 overflow-y-auto pr-1">
      {logs.map((log) => {
        const style = LEVEL_STYLE[log.level];
        const node = NODE_MAP.get(log.nodeId);
        const expandable = log.level === "decision" && log.detail;
        const open = openId === log.id;
        return (
          <div key={log.id} className="rounded-lg px-2 py-1.5 hover:bg-panel">
            <button
              type="button"
              className={cn("flex w-full items-start gap-2 text-left", expandable && "cursor-pointer")}
              onClick={() => expandable && setOpenId(open ? null : log.id)}
              disabled={!expandable}
            >
              <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", style.dot)} />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-1.5">
                  <span className="shrink-0 font-mono text-[10px] text-faint">{log.time}</span>
                  <span className="shrink-0 text-[10px] text-faint">
                    {node ? `${node.index}${node.label}` : ""} · {log.source}
                  </span>
                  {expandable && (
                    <ChevronDown className={cn("size-3 shrink-0 text-faint transition-transform", open && "rotate-180")} />
                  )}
                </span>
                <span className={cn("block text-xs leading-5", style.label)}>{log.text}</span>
              </span>
            </button>
            {open && log.detail && (
              <p className="mt-1 ml-3.5 rounded-lg bg-chip px-2.5 py-2 text-[11px] leading-5 text-muted">
                决策理由:{log.detail}
              </p>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
