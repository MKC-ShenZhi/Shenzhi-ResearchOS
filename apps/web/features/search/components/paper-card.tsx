"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Bookmark, Plus, ThumbsUp, TrendingUp, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useUserPreferences } from "@/stores/user-preferences";
import type { FeedPaper } from "@/types";

const VENUE_VARIANT = { violet: "violet", amber: "amber", green: "green" } as const;

/** 论文卡片 —— 对应主发现页 SVG 的 Feed 卡片 */
export function PaperCard({
  paper,
  index,
  layout = "feed",
}: {
  paper: FeedPaper;
  index: number;
  layout?: "feed" | "explore";
}) {
  const { likedPapers, bookmarkedPapers, toggleLike, toggleBookmark } =
    useUserPreferences();
  const liked = !!likedPapers[paper.id];
  const bookmarked = !!bookmarkedPapers[paper.id];

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.08 }}
      className="rounded-2xl bg-card p-6 shadow-card"
    >
      <div className="flex gap-6">
        <div className="min-w-0 flex-1">
          {/* 元信息行 */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
            <span className="text-faint">{paper.date}</span>
            <Badge variant={VENUE_VARIANT[paper.venueTone]}>{paper.venue}</Badge>
            <span className="flex items-center gap-1.5 text-muted">
              <Users className="size-3.5 text-faint" />
              {paper.authors}
            </span>
          </div>

          {/* 标题 */}
          <Link href={`/papers/${encodeURIComponent(paper.id)}`} className="group mt-2 block">
            <h3 className="text-[17px] font-bold leading-snug text-ink transition-colors group-hover:text-primary">
              {paper.title}
            </h3>
          </Link>

          {/* 摘要 */}
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted">
            {paper.abstract}
          </p>

          {/* AI 解读入口 */}
          <Link
            href={`/papers/${encodeURIComponent(paper.id)}`}
            className="mt-2 inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"
          >
            <Plus className="size-3.5" />
            {paper.aiLink}
            <ArrowRight className="size-3.5" />
          </Link>

          {/* 底部操作行 */}
          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {paper.tags.map((tag) => (
                <span key={tag} className="text-[13px] text-muted">
                  #{tag}
                </span>
              ))}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => toggleLike(paper.id)}
                className={
                  "flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] transition-colors " +
                  (liked ? "text-primary" : "text-muted hover:bg-chip")
                }
              >
                <ThumbsUp className="size-4" fill={liked ? "currentColor" : "none"} />
                {paper.likes + (liked ? 1 : 0)}
              </button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toggleBookmark(paper.id)}
                className={bookmarked ? "text-primary" : undefined}
              >
                <Bookmark className="size-4" fill={bookmarked ? "currentColor" : "none"} />
                收藏
              </Button>
              {layout === "feed" && (
                <Link href={`/papers/${encodeURIComponent(paper.id)}`}>
                  <Button size="sm" className="h-9 rounded-lg px-4 text-[13px]">
                    立即阅读
                    <ArrowRight className="size-3.5" />
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </div>

        {layout === "feed" && (
          <div className="relative hidden w-[200px] shrink-0 md:block">
            <div className="absolute -top-2 right-2 z-10 flex items-center gap-1 rounded-full bg-card px-2.5 py-1 text-xs text-muted shadow-card">
              <TrendingUp className="size-3 text-primary" />
              引用 {paper.citations}
            </div>
            <div className="flex h-full min-h-[128px] items-center justify-center rounded-xl bg-chip text-sm text-faint">
              {paper.thumb}
            </div>
          </div>
        )}
      </div>
    </motion.article>
  );
}
