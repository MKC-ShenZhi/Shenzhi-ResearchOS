"use client";

import { Search, Sparkles } from "lucide-react";

/** 论文库顶部 —— 保留现有论文检索能力。 */
export function KnowledgeSearchHero({
  initialQuery,
  onQueryChange,
  onSearch,
}: {
  initialQuery: string;
  onQueryChange: (value: string) => void;
  onSearch: (query: string) => void;
}) {
  return (
    <header>
      <div className="flex items-center gap-2.5">
        <h1 className="text-2xl font-bold tracking-tight text-ink">论文库</h1>
        <span className="rounded-full bg-primary-soft px-2.5 py-1 text-[11px] font-medium text-primary">
          知识底座
        </span>
      </div>
      <p className="mt-1.5 text-sm text-muted">
        从知识底座科研数据库中检索论文，找到感兴趣的工作后可继续探索关系图谱
      </p>

      <form
        className="relative mt-5"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch(initialQuery);
        }}
      >
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-card px-4 py-1 shadow-card focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/15">
          <Search className="size-5 shrink-0 text-faint" />
          <input
            value={initialQuery}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="搜索论文标题、作者、关键词… 例如 Diffusion Policy"
            className="h-12 min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-faint"
            autoFocus
          />
          <span className="hidden shrink-0 items-center gap-1 text-[11px] text-faint md:flex">
            <Sparkles className="size-3.5" /> 论文数据库
          </span>
          <button
            type="submit"
            className="h-9 shrink-0 rounded-xl bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-deep"
          >
            开始检索
          </button>
        </div>
        <p className="mt-2 px-1 text-[11px] text-faint">
          检索范围：论文 / 会议等学术资源
        </p>
      </form>
    </header>
  );
}
