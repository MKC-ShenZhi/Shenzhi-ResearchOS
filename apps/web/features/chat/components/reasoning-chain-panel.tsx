"use client";

import { useState } from "react";
import { BrainCircuit, ChevronDown, ChevronRight } from "lucide-react";

/** R1 / reasoning 模型流式思考链展示 */
export function ReasoningChainPanel({
  content,
  streaming,
}: {
  content: string;
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(false);

  const tokens = Array.from(content).length;
  if (!content) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-primary/20 bg-primary-soft/40">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left"
      >
        {open ? (
          <ChevronDown className="size-3.5 text-faint" />
        ) : (
          <ChevronRight className="size-3.5 text-faint" />
        )}
        <BrainCircuit className="size-3.5 text-primary" />
        <span className="text-[12px] font-medium text-ink-2">深度思考</span>
        <span className="ml-1 rounded-md bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium text-primary">
          {streaming ? "思考中…" : "已完成"}
        </span>
        <span className="ml-auto text-[11px] text-faint">已生成 {tokens} 字</span>
      </button>
      {open && (
        <div className="border-t border-primary/10 bg-white/50 p-3 dark:bg-card/50">
          <div className="max-h-[380px] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-white/80 p-3 text-[12.5px] leading-6 text-ink-2 shadow-inner ring-1 ring-line/60 dark:bg-card">
            {content}
            {streaming && (
              <span className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-primary align-[-2px]" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
