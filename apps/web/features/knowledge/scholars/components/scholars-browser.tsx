"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Network, Search } from "lucide-react";
import { ScholarCard } from "./scholar-card";
import { DirectionFilter } from "./direction-filter";
import { useDebounce } from "@/hooks/use-debounce";
import { scholars } from "@/features/knowledge/data-scholars";
import { cn } from "@/lib/utils";

const SORTS = [
  { key: "top", label: "Top 引用" },
  { key: "recent", label: "近期活跃" },
  { key: "followed", label: "已关注" },
];

/** 学者浏览区 —— 搜索防抖过滤 + 排序切换(README 5.2 交互增强) */
export function ScholarsBrowser() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("top");
  const [direction, setDirection] = useState<string | null>(null);
  const debouncedQuery = useDebounce(query, 300);

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase();
    let list = scholars;
    if (direction) list = list.filter((s) => s.tags.includes(direction));
    if (sort === "followed") list = list.filter((s) => s.followed);
    if (q) {
      list = list.filter((s) =>
        [s.nameCn, s.nameEn, s.affiliation, ...s.tags]
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    return list;
  }, [debouncedQuery, direction, sort]);

  return (
    <>
      <DirectionFilter activeDirection={direction} onDirectionChange={setDirection} />
      <div className="min-w-0 flex-1 space-y-5 px-8 py-6">
      {/* 顶部横幅:探索学者关系图谱 */}
      <section className="flex items-center justify-between rounded-2xl bg-card px-8 py-7 shadow-card">
        <div className="flex items-center gap-4">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-primary-soft">
            <Network className="size-6 text-primary" />
          </span>
          <div>
            <p className="text-[15px] font-semibold text-ink">学者关系图谱</p>
            <p className="mt-0.5 text-xs text-muted">
              从合作网络与引用脉络中发现关键学者
            </p>
          </div>
        </div>
        <Link href="/knowledge/scholars/graph" className="inline-flex h-9 items-center gap-1.5 rounded-full border border-primary/40 px-4 text-[13px] font-medium text-primary transition-colors hover:bg-primary-soft">
          探索学者关系图谱
          <span aria-hidden>→</span>
        </Link>
      </section>

      {/* 搜索 + 排序 */}
      <div className="flex items-center gap-3">
        <div className="relative w-full max-w-[420px]">
          <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索学者姓名、机构或研究关键词…"
            className="h-10 w-full rounded-xl border border-line bg-card pl-10 pr-4 text-sm text-ink outline-none transition-colors placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
          />
        </div>
        <div className="ml-auto flex gap-2">
          {SORTS.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setSort(s.key)}
              className={cn(
                "h-9 cursor-pointer rounded-full border px-4 text-[13px] transition-colors",
                sort === s.key
                  ? "border-primary font-medium text-primary"
                  : "border-line bg-card text-muted hover:text-ink-2",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* 双列卡片 */}
      <div className="grid gap-5 xl:grid-cols-2">
        {filtered.map((scholar, i) => (
          <ScholarCard key={scholar.id} scholar={scholar} index={i} />
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">
          未找到匹配的学者
        </div>
      )}
      </div>
    </>
  );
}
