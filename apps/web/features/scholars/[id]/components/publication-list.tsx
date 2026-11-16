"use client";

import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { scholarDetail } from "@/features/knowledge/data-scholars";

const TABS = ["Top 引用", "近期热门", "最新"];

/** 研究成果 —— 论文列表 + 排序标签 + 分页 */
export function PublicationList() {
  const [tab, setTab] = useState(TABS[0]);

  return (
    <section className="rounded-2xl bg-card p-6 shadow-card">
      <div className="flex items-center justify-between">
        <h2 className="text-[17px] font-bold text-ink">
          研究成果
          <span className="ml-2 text-sm font-normal text-faint">84</span>
        </h2>
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "h-8 cursor-pointer rounded-lg px-3 text-[13px] transition-colors",
                tab === t
                  ? "bg-primary-soft font-medium text-primary"
                  : "text-muted hover:text-ink-2",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 space-y-6">
        {scholarDetail.publications.map((pub) => (
          <article key={pub.id} className="flex gap-5">
            <div className="flex h-[140px] w-[110px] shrink-0 items-center justify-center rounded-lg bg-chip text-xs text-faint">
              论文缩略图
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-[15px] font-bold leading-snug text-ink">
                {pub.title}
              </h3>
              <p className="mt-1.5 line-clamp-3 text-[13px] leading-relaxed text-muted">
                {pub.abstract}
              </p>
              <p className="mt-2 text-xs text-faint">
                {pub.authors} · {pub.venue}
              </p>
              <div className="mt-2 flex items-center gap-3 text-[13px]">
                <span className="font-semibold text-primary">{pub.citations}</span>
                <span className="text-xs text-muted">{pub.citationsShort}</span>
                <button
                  type="button"
                  className="flex cursor-pointer items-center gap-1 text-xs font-medium text-primary hover:underline"
                >
                  查看
                  <ArrowRight className="size-3" />
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="mt-6 flex items-center justify-center gap-3">
        <span className="text-xs text-faint">第 1 / 9 页</span>
        <Button variant="outline" size="sm" disabled>
          上一页
        </Button>
        <Button variant="outline" size="sm">
          下一页
          <ArrowRight className="size-3.5" />
        </Button>
      </div>
    </section>
  );
}
