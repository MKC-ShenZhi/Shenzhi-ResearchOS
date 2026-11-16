"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CollectionPicker } from "@/features/knowledge/papers/components/collection-picker";
import { PaperCardLayout } from "@/features/knowledge/papers/components/paper-card-layout";
import { PaperCollectorCount } from "@/features/knowledge/interactions/components/paper-collector-count";
import { PaperLikeButton } from "@/features/knowledge/interactions/components/paper-like-button";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { paperHref } from "@/lib/navigation/paper";
import type { FeedPaper } from "@/types";
import { useAuth } from "@/components/auth/auth-provider";
import { recordPaperBehavior } from "@/clients/backend/behavior";

/** 首页 Feed 卡片：发现 / 推荐的曝光与点击埋点，版式见 PaperCardLayout。 */
export function PaperCard({
  paper,
  index,
}: {
  paper: FeedPaper;
  index: number;
}) {
  const returnTo = useCurrentInternalPath();
  const { session } = useAuth();
  const userId = session?.user.id ?? "";
  const articleRef = useRef<HTMLElement>(null);
  const impressionSent = useRef(false);
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
    <PaperCardLayout
      paper={paper}
      index={index}
      detailHref={detailHref}
      onNavigate={trackClick}
      behaviorSource={source}
      articleRef={articleRef}
      deferOffscreen
      actions={
        <>
          <PaperLikeButton paperId={paper.id} />
          <PaperCollectorCount paperId={paper.id} />
          <CollectionPicker paperId={paper.id} />
          <Link href={detailHref} onClick={trackClick}>
            <Button size="sm" className="h-9 rounded-lg px-4 text-[13px]">
              立即阅读
              <ArrowRight className="size-3.5" />
            </Button>
          </Link>
        </>
      }
    />
  );
}
