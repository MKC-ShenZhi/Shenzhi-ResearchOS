"use client";

import { AlertTriangle, Inbox, RotateCw, SearchX, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { KnowledgeClientError } from "@/clients/knowledge";

/** 搜索加载骨架屏 */
export function KnowledgeSearchSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="正在检索论文">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="rounded-2xl bg-card p-6 shadow-card">
          <div className="flex items-center gap-3">
            <div className="h-3 w-10 animate-pulse rounded bg-chip" />
            <div className="h-5 w-16 animate-pulse rounded-full bg-chip" />
            <div className="h-3 w-40 animate-pulse rounded bg-chip" />
          </div>
          <div className="mt-3 h-5 w-3/4 animate-pulse rounded bg-chip" />
          <div className="mt-2 h-3 w-full animate-pulse rounded bg-chip" />
          <div className="mt-2 h-3 w-2/3 animate-pulse rounded bg-chip" />
          <div className="mt-4 flex items-center gap-2">
            {Array.from({ length: 4 }).map((_, tag) => (
              <div key={tag} className="h-4 w-12 animate-pulse rounded-full bg-chip" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/** 无搜索结果（≠ 服务不可用） */
export function KnowledgeSearchEmpty({ query }: { query: string }) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-2xl bg-card px-6 py-12 text-center shadow-card">
      <span className="flex size-12 items-center justify-center rounded-full bg-panel text-faint">
        <SearchX className="size-6" />
      </span>
      <p className="mt-4 text-sm font-medium text-ink-2">没有找到与「{query}」相关的论文</p>
      <p className="mt-2 max-w-sm text-xs leading-relaxed text-faint">
        尝试更换关键词、减少筛选条件，或使用英文关键词检索
      </p>
    </div>
  );
}

/** 检索错误（知识底座服务不可用等） */
export function KnowledgeSearchError({
  error,
  onRetry,
}: {
  error: KnowledgeClientError;
  onRetry: () => void;
}) {
  const unavailable = ["UPSTREAM_UNAVAILABLE", "TIMEOUT", "RATE_LIMITED"].includes(error.code);
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-2xl bg-card px-6 py-12 text-center shadow-card">
      <span
        className={
          "flex size-12 items-center justify-center rounded-full " +
          (unavailable ? "bg-danger-soft text-danger" : "bg-warning-soft text-warning")
        }
      >
        {unavailable ? <WifiOff className="size-6" /> : <AlertTriangle className="size-6" />}
      </span>
      <p className="mt-4 text-sm font-medium text-ink-2">
        {unavailable ? "知识底座服务暂不可用" : "检索失败"}
      </p>
      <p className="mt-2 max-w-sm text-xs leading-relaxed text-faint">{error.message}</p>
      <Button size="sm" variant="outline" className="mt-5" onClick={onRetry}>
        <RotateCw className="size-3.5" />
        重新检索
      </Button>
    </div>
  );
}

/** 空态兜底（无查询词） */
export function KnowledgeSearchIdle() {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-card/40 px-6 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-panel text-faint">
        <Inbox className="size-6" />
      </span>
      <p className="mt-4 text-sm font-medium text-ink-2">暂无检索内容</p>
      <p className="mt-2 max-w-sm text-xs leading-relaxed text-faint">
        在左侧输入关键词开始检索论文，结果将展示在这里
      </p>
    </div>
  );
}
