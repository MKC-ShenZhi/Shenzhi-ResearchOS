"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Plus, ThumbsUp, TrendingUp, Users } from "lucide-react";
import { PaperThumbnail } from "@/components/common/paper-thumbnail";
import { PAPER_CARD_INTERACTION_CLASS, usePaperCardNavigation } from "@/components/common/use-paper-card-navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollectionPicker } from "@/features/knowledge/papers/components/collection-picker";
import { PaperReadBadge } from "@/features/knowledge/papers/components/paper-read-badge";
import { usePaperReadStatus } from "@/features/knowledge/papers/use-paper-read-status";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { paperHref } from "@/lib/navigation/paper";
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
  const returnTo = useCurrentInternalPath();
  const [collectionPickerOpen, setCollectionPickerOpen] = useState(false);
  const { likedPapers, toggleLike } = useUserPreferences();
  const liked = !!likedPapers[paper.id];
  const status = usePaperReadStatus(paper.id);
  const detailHref = paperHref(paper.id, { mode: "create", source: returnTo });
  const cardNavigation = usePaperCardNavigation(detailHref, paper.title);

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: (index % 12) * 0.03 }}
      className={`@container relative rounded-2xl bg-card p-6 shadow-card [overflow-wrap:anywhere] ${collectionPickerOpen ? "z-30" : ""} ${PAPER_CARD_INTERACTION_CLASS}`}
      {...cardNavigation}
    >
      <div className={layout === "feed" ? "grid grid-cols-1 items-start gap-x-6 gap-y-4 @min-[600px]:grid-cols-[minmax(0,1fr)_clamp(200px,30cqw,280px)]" : "grid grid-cols-1 gap-y-4"}>
        <div className="min-w-0">
          {/* 元信息行 */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
            <span className="text-faint">{paper.date}</span>
            <Badge variant={VENUE_VARIANT[paper.venueTone]}>{paper.venue}</Badge>
            {status && <PaperReadBadge status={status} />}
            <span className="flex min-w-0 items-center gap-1.5 text-muted">
              <Users className="size-3.5 shrink-0 text-faint" />
              <span className="min-w-0">{paper.authors}</span>
            </span>
          </div>

          {/* 标题 */}
          <Link href={detailHref} className="group mt-2 block">
            <h3 className="line-clamp-2 text-[17px] font-bold leading-snug text-ink transition-colors group-hover:text-primary">
              {paper.title}
            </h3>
          </Link>
          {/* 摘要 */}
          <p className="mt-3 line-clamp-4 text-sm leading-relaxed text-muted">
            {paper.abstract}
          </p>

          {/* AI 解读入口 */}
          <Link
            href={detailHref}
            className="mt-2 inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"
          >
            <Plus className="size-3.5" />
            {paper.aiLink}
            <ArrowRight className="size-3.5" />
          </Link>
        </div>

        {layout === "feed" && (
          <div className="w-full max-w-[280px] justify-self-center self-start">
            <PaperThumbnail src={paper.thumbnailUrl} title={paper.title} eager={index < 2} aspectRatio={7 / 5} />
            {paper.citations !== undefined && (
              <div className="mt-2 flex items-center justify-end gap-1 text-xs text-muted">
                <TrendingUp className="size-3 text-primary" />
                引用 {paper.citations}
              </div>
            )}
          </div>
        )}

        {/* 底部操作行 */}
        <div className="col-span-full flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex flex-wrap gap-x-4 gap-y-1">
            {paper.tags.map((tag) => (
              <span key={tag} className="text-[13px] text-muted">
                #{tag}
              </span>
            ))}
          </div>
          <div className="ml-auto flex max-w-full flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => toggleLike(paper.id)}
              className={
                "flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] transition-colors " +
                (liked ? "text-primary" : "text-muted hover:bg-chip")
              }
            >
              <ThumbsUp className="size-4" fill={liked ? "currentColor" : "none"} />
              {paper.likes !== undefined && paper.likes + (liked ? 1 : 0)}
            </button>
            <CollectionPicker className="order-last sm:order-none" paperId={paper.id} onOpenChange={setCollectionPickerOpen} />
            {layout === "feed" && (
              <Link href={detailHref}>
                <Button size="sm" className="h-9 rounded-lg px-4 text-[13px]">
                  立即阅读
                  <ArrowRight className="size-3.5" />
                </Button>
              </Link>
            )}
          </div>
        </div>
      </div>
    </motion.article>
  );
}
