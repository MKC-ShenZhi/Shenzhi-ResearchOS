"use client";

import { useMemo, useState } from "react";
import { Search, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { libraryItems } from "@/lib/data/library";
import { cn } from "@/lib/utils";

const PDF_TONES = {
  violet: "bg-primary-soft text-primary",
  amber: "bg-[#FEF3C7] text-[#B45309] dark:bg-[#3a2f10] dark:text-[#f0c94e]",
  green: "bg-success-soft text-[#059669] dark:text-success",
} as const;

/** 在读文献表格 —— 标题 / 作者 / 添加时间 */
export function LibraryTable() {
  const [query, setQuery] = useState("");
  const [venue, setVenue] = useState("全部会议");
  const [year, setYear] = useState("全部年份");

  const venues = ["全部会议", ...new Set(libraryItems.map((item) => item.venue.split(" ")[0]))];
  const years = ["全部年份", ...new Set(libraryItems.map((item) => item.venue.match(/\d{4}/)?.[0] ?? "其他"))];
  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return libraryItems.filter((item) => {
      const itemVenue = item.venue.split(" ")[0];
      const itemYear = item.venue.match(/\d{4}/)?.[0] ?? "其他";
      if (venue !== "全部会议" && itemVenue !== venue) return false;
      if (year !== "全部年份" && itemYear !== year) return false;
      return !keyword || `${item.title} ${item.authors} ${item.venue} ${item.arxiv}`.toLowerCase().includes(keyword);
    });
  }, [query, venue, year]);

  return (
    <div className="min-w-0 flex-1 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">在读</h1>
          <p className="mt-1 text-xs text-faint">
            12 篇文献 · 上次更新 7 月 25 日
          </p>
        </div>
        <Button className="rounded-xl">
          <Upload className="size-4" />
          上传私有论文
        </Button>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2.5">
        <div className="relative min-w-[280px] max-w-[460px] flex-1">
          <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索论文的标题/作者/会议"
            className="h-10 w-full rounded-xl border border-line bg-card pl-10 pr-4 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15"
          />
        </div>
        <select value={venue} onChange={(event) => setVenue(event.target.value)} className="h-10 rounded-xl border border-line bg-card px-3 text-xs text-ink-2 outline-none">
          {venues.map((item) => <option key={item}>{item}</option>)}
        </select>
        <select value={year} onChange={(event) => setYear(event.target.value)} className="h-10 rounded-xl border border-line bg-card px-3 text-xs text-ink-2 outline-none">
          {years.map((item) => <option key={item}>{item}</option>)}
        </select>
        <span className="text-xs text-faint">找到 {filtered.length} 篇</span>
      </div>

      {/* 表头 */}
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)_220px_90px] items-center gap-4 rounded-xl bg-card px-5 py-3 text-xs text-faint shadow-card">
        <span className="flex items-center gap-3">
          <span className="size-4 rounded border border-line" />
          标题
        </span>
        <span>作者</span>
        <span>添加时间</span>
      </div>

      {/* 数据行 */}
      <div className="mt-3 space-y-2">
        {filtered.map((item) => (
          <div
            key={item.id}
            className="grid cursor-pointer grid-cols-[minmax(0,1fr)_220px_90px] items-center gap-4 rounded-xl px-5 py-3 transition-colors hover:bg-card"
          >
            <div className="flex min-w-0 items-center gap-3">
              <span className="size-4 shrink-0 rounded border border-line bg-card" />
              <span
                className={cn(
                  "flex h-11 w-9 shrink-0 items-end justify-center rounded-md pb-1 text-[10px] font-bold",
                  PDF_TONES[item.pdfTone],
                )}
              >
                PDF
              </span>
              <div className="min-w-0">
                <p className="truncate text-[15px] font-semibold text-ink">
                  {item.title}
                </p>
                <p className="mt-0.5 text-xs text-faint">
                  {item.venue} · {item.arxiv}
                </p>
              </div>
            </div>
            <p className="truncate text-[13px] text-muted">{item.authors}</p>
            <p className="text-[13px] text-muted">{item.addedAt}</p>
          </div>
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="mt-3 rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">未找到匹配的文献</div>
      )}
    </div>
  );
}
