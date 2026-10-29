"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Plus, TrendingUp, Users } from "lucide-react";
import { PaperThumbnail } from "@/components/common/paper-thumbnail";
import { PAPER_CARD_INTERACTION_CLASS, usePaperCardNavigation } from "@/components/common/use-paper-card-navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollectionPicker } from "@/features/knowledge/papers/components/collection-picker";
import { PaperCollectorCount } from "@/features/knowledge/interactions/components/paper-collector-count";
import { PaperLikeButton } from "@/features/knowledge/interactions/components/paper-like-button";
import { PaperReadBadge } from "@/features/knowledge/papers/components/paper-read-badge";
import { usePaperReadStatus } from "@/features/knowledge/papers/use-paper-read-status";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { paperHref } from "@/lib/navigation/paper";
import type { FeedPaper } from "@/types";
import { useAuth } from "@/components/auth/auth-provider";
import { recordPaperBehavior } from "@/clients/backend/behavior";
import { ExpandableAbstract } from "@/components/common/expandable-abstract";

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
  const { session } = useAuth();
  const userId = session?.user.id ?? "";
  const articleRef = useRef<HTMLElement>(null);
  const impressionSent = useRef(false);
  const status = usePaperReadStatus(paper.id);
  const detailHref = paperHref(paper.id, { mode: "create", source: returnTo });
  const source = paper.recommendationRequestId ? "recommendation" : "discovery";
  const trackClick = () => {
    if (!userId) return;
    recordPaperBehavior({
      userId,
      eventType: source === "recommendation" ? "recommendation_click" : "paper_click",
      paperId: paper.id, source,
      requestId: paper.recommendationRequestId,
      rank: paper.recommendationRank,
    });
  };
  const cardNavigation = usePaperCardNavigation(detailHref, paper.title, trackClick);

  useEffect(() => {
    const element = articleRef.current;
    if (!element || !userId || impressionSent.current) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let visibleEnough = false;
    const clearTimer = () => {
      if (timer) clearTimeout(timer);
      timer = undefined;
    };
    const updateTimer = () => {
      if (!visibleEnough || document.visibilityState !== "visible") {
        clearTimer();
        return;
      }
      if (timer || impressionSent.current) return;
      timer = setTimeout(() => {
        timer = undefined;
        if (document.visibilityState !== "visible" || !visibleEnough || impressionSent.current) return;
        impressionSent.current = true;
        recordPaperBehavior({
          userId,
          eventType: source === "recommendation" ? "recommendation_impression" : "paper_impression",
          paperId: paper.id, source,
          requestId: paper.recommendationRequestId,
          rank: paper.recommendationRank,
        });
      }, 1000);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visibleEnough = Boolean(entry && entry.intersectionRatio >= 0.5);
      updateTimer();
    }, { threshold: 0.5 });
    observer.observe(element);
    document.addEventListener("visibilitychange", updateTimer);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", updateTimer); clearTimer(); };
  }, [paper.id, paper.recommendationRank, paper.recommendationRequestId, userId, source]);

  return (
    <motion.article
      ref={articleRef}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: (index % 12) * 0.03 }}
      className={`@container relative rounded-2xl bg-card p-6 shadow-card [overflow-wrap:anywhere] [contain-intrinsic-size:auto_260px] [content-visibility:auto] has-[[data-collection-picker-open]]:z-40 has-[[data-collection-picker-open]]:[content-visibility:visible] ${PAPER_CARD_INTERACTION_CLASS}`}
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
          <Link href={detailHref} onClick={trackClick} className="group mt-2 block">
            <h3 className="line-clamp-2 text-[17px] font-bold leading-snug text-ink transition-colors group-hover:text-primary">
              {paper.title}
            </h3>
          </Link>
          {/* 摘要 */}
          <ExpandableAbstract
            abstract={paper.abstract}
            paperId={paper.id}
            source={source}
            userId={userId}
            className="mt-3 text-sm leading-relaxed text-muted"
            collapsedClassName="line-clamp-4"
          />
          {paper.recommendationReason && (
            <p className="mt-2 text-xs text-primary">{paper.recommendationReason}</p>
          )}

          {/* AI 解读入口 */}
          <Link
            href={detailHref}
            onClick={trackClick}
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
            <PaperLikeButton paperId={paper.id} />
            <PaperCollectorCount paperId={paper.id} />
            <CollectionPicker paperId={paper.id} />
            {layout === "feed" && (
              <Link href={detailHref} onClick={trackClick}>
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
