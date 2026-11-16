"use client";

import { useCallback, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { InstitutionCard } from "./institution-card";
import { useDebounce } from "@/hooks/use-debounce";
import { institutions } from "@/features/knowledge/data-institutions";
import { useUserPreferences } from "@/stores/user-preferences";
import { cn } from "@/lib/utils";
import type { Institution } from "@/types";

const SORTS = [
  { key: "rank", label: "综合排名" },
  { key: "papers", label: "论文数" },
  { key: "bookmarked", label: "已收藏" },
];

/** 机构浏览区 —— 搜索 + 排序 + 单列大卡片 */
export function InstitutionsBrowser() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("rank");
  const [type, setType] = useState<string | null>(null);
  const debouncedQuery = useDebounce(query, 300);
  const { bookmarkedInstitutions } = useUserPreferences();

  const isBookmarked = useCallback(
    (i: Institution) => bookmarkedInstitutions[i.id] ?? i.bookmarked ?? false,
    [bookmarkedInstitutions],
  );

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase();
    let list = institutions;
    if (type) list = list.filter((i) => i.type === type);
    if (sort === "bookmarked") list = list.filter((i) => isBookmarked(i));
    if (q) {
      list = list.filter((i) =>
        [i.nameCn, i.nameEn, i.location, ...i.fields]
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    return [...list].sort((a, b) =>
      sort === "papers" ? b.papersPerYear - a.papersPerYear : a.rank - b.rank,
    );
  }, [debouncedQuery, sort, isBookmarked, type]);

  return (
    <div className="space-y-5">
      {/* 搜索 + 排序 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-[420px]">
          <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索机构名称、地点或研究方向…"
            aria-label="搜索研究机构"
            className="h-10 w-full rounded-xl border border-line bg-card pl-10 pr-4 text-sm text-ink outline-none transition-colors placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
          />
        </div>
        <div className="flex gap-1.5">
          {[null, "高校", "研究院", "企业实验室"].map((item) => (
            <button key={item ?? "all"} type="button" onClick={() => setType(item)} className={cn("h-9 rounded-full border px-3 text-xs transition-colors", type === item ? "border-primary bg-primary-soft font-medium text-primary" : "border-line bg-card text-muted hover:text-ink")}>{item ?? "全部类型"}</button>
          ))}
        </div>
        <div className="ml-auto flex gap-2">
          {SORTS.map((s) => (
            <button
              key={s.key}
              type="button"
              aria-pressed={sort === s.key}
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

      {/* 单列大卡片 */}
      <div className="space-y-6">
        {filtered.map((institution, i) => (
          <InstitutionCard key={institution.id} institution={institution} index={i} />
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">
          未找到匹配的机构
        </div>
      )}
    </div>
  );
}
