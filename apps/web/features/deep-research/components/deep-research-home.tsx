"use client";

import { useState } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  drHistory,
  drScopeOptions,
  drSuggestions,
} from "@/features/deep-research/data";
import { cn } from "@/lib/utils";

/** Deep Research 入口态 —— Hero + 研究问题输入 + 建议主题 + 历史研究 */
export function DeepResearchHome({
  onStart,
  onOpenHistory,
}: {
  onStart: (question: string) => void;
  onOpenHistory: () => void;
}) {
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<string>(drScopeOptions[0]);

  const start = () => {
    const q = value.trim();
    if (q) onStart(q);
  };

  return (
    <div className="mx-auto max-w-[760px] px-6 pb-16 pt-14">
      {/* Hero */}
      <div className="text-center">
        <span aria-hidden="true" className="mx-auto flex size-11 items-center justify-center rounded-2xl bg-primary">
          <Sparkles className="size-5 text-white" />
        </span>
        <h1 className="mt-4 text-2xl font-bold text-ink">Deep Research</h1>
        <p className="mt-2 text-sm text-muted">
          围绕一个问题,阅读数十篇文献,产出带引用的研究报告
        </p>
      </div>

      {/* 研究问题输入卡 */}
      <div className="mt-8 rounded-2xl bg-card p-4 shadow-card">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={3}
          autoFocus
          placeholder="输入你的研究问题,例如:扩散模型在机器人策略学习中最近有哪些突破性进展?"
          className="w-full resize-none bg-transparent text-[15px] leading-relaxed text-ink outline-none placeholder:text-faint"
        />
        <div className="mt-3 flex items-center gap-2 border-t border-line pt-3">
          {drScopeOptions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              className={cn(
                "flex h-8 cursor-pointer items-center rounded-full px-3.5 text-[13px] transition-colors",
                scope === s
                  ? "bg-primary-soft font-medium text-primary"
                  : "text-muted hover:bg-chip",
              )}
            >
              {s}
            </button>
          ))}
          <Button
            onClick={start}
            disabled={!value.trim()}
            className="ml-auto rounded-xl"
          >
            开始研究
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </div>

      {/* 建议主题(点击填入输入框) */}
      <div className="mt-4 flex flex-wrap justify-center gap-2.5">
        {drSuggestions.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setValue(s)}
            className="flex h-9 cursor-pointer items-center rounded-full border border-line bg-card px-4 text-[13px] text-ink-2 transition-colors hover:border-primary hover:text-primary"
          >
            {s}
          </button>
        ))}
      </div>

      {/* 历史研究(原型:全部加载同一份示例报告的完成态) */}
      <p className="mt-10 text-xs text-faint">历史研究</p>
      <div className="mt-2.5 grid gap-3 sm:grid-cols-2">
        {drHistory.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={onOpenHistory}
            className="cursor-pointer rounded-2xl bg-card p-4 text-left shadow-card transition-shadow hover:shadow-pop"
          >
            <div className="flex items-center gap-2">
              <span className="block min-w-0 flex-1 truncate text-[14px] font-medium text-ink">
                {item.title}
              </span>
              <span
                className={cn(
                  "shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                  item.status === "已完成"
                    ? "bg-success-soft text-success"
                    : "bg-primary-soft text-primary",
                )}
              >
                {item.status}
              </span>
            </div>
            <span className="mt-1.5 block text-[11px] text-faint">
              {item.sources} 来源 · {item.time}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
