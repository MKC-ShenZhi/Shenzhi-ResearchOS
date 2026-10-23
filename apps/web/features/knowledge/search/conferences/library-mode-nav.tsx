"use client";

import { SearchNavigationLink } from "@/components/common/layout/search-navigation-link";

export function LibraryModeNav({ mode }: { mode: "keyword" | "conference" }) {
  return (
    <nav className="my-6 flex gap-2 border-b border-line pb-3" aria-label="论文查询模式">
      {([
        ["conference", "按会议浏览", "/knowledge/search?mode=conference"],
        ["keyword", "关键词检索", "/knowledge/search?mode=keyword"],
      ] as const).map(([value, label, href]) => (
        <SearchNavigationLink key={value} href={href} aria-current={mode === value ? "page" : undefined}
          className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${mode === value ? "bg-primary text-primary-foreground" : "text-muted hover:bg-panel hover:text-ink"}`}>
          {label}
        </SearchNavigationLink>
      ))}
    </nav>
  );
}
