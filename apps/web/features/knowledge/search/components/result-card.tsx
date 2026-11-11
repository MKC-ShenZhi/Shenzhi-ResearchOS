"use client";

import Link from "next/link";
import { ArrowRight, Network } from "lucide-react";
import type { KnowledgePaperHit } from "@/clients/knowledge";
import { useAuth } from "@/components/auth/auth-provider";
import { recordPaperBehavior } from "@/clients/backend/behavior";
import { Button } from "@/components/ui/button";
import { paperHref } from "@/lib/navigation/paper";
import { getPaperThumbnailUrl } from "@/lib/paper-thumbnail";
import { CollectionPicker } from "@/features/knowledge/papers/components/collection-picker";
import { PaperCardLayout } from "@/features/knowledge/papers/components/paper-card-layout";
import {
  formatPaperAuthors,
  formatPaperYear,
  paperVenueTone,
  pickPaperTopics,
} from "@/features/knowledge/papers/paper-card-model";
import { PaperCollectorCount } from "@/features/knowledge/interactions/components/paper-collector-count";
import { PaperLikeButton } from "@/features/knowledge/interactions/components/paper-like-button";
import type { PaperCardModel } from "@/types";

function toPaperCardModel(hit: KnowledgePaperHit): PaperCardModel {
  return {
    id: hit.id,
    date: formatPaperYear(hit.year),
    venue: hit.venue,
    venueTone: paperVenueTone(hit.id),
    authors: formatPaperAuthors(hit.authors),
    title: hit.title,
    abstract: hit.abstract ?? "",
    topics: pickPaperTopics(hit.topics),
    thumbnailUrl: getPaperThumbnailUrl(hit.imageId),
  };
}

/** 论文搜索结果卡片：检索点击埋点与详情 / 图谱入口，版式见 PaperCardLayout。 */
export function KnowledgeResultCard({
  hit,
  index,
  returnTo,
  queryId,
  historyMode = false,
  lastViewedAt,
  onNavigate,
}: {
  hit: KnowledgePaperHit;
  index: number;
  returnTo: string;
  queryId?: string;
  historyMode?: boolean;
  lastViewedAt?: string;
  onNavigate?: () => void;
}) {
  const { session } = useAuth();
  const userId = session?.user.id ?? "";
  const trackSearchClick = () => {
    if (userId && returnTo.startsWith("/knowledge/search") && !historyMode) {
      recordPaperBehavior({ userId, eventType: "search_result_click", paperId: hit.id, source: "search", rank: index + 1, queryId });
    }
    onNavigate?.();
  };
  const detailHref = paperHref(hit.id, { mode: "create", source: returnTo });

  return (
    <PaperCardLayout
      paper={toPaperCardModel(hit)}
      index={index}
      detailHref={detailHref}
      onNavigate={trackSearchClick}
      behaviorSource="search"
      actions={historyMode ? (
        <time dateTime={lastViewedAt} className="text-xs text-faint">
          上次浏览：{lastViewedAt ? formatLastViewedAt(lastViewedAt) : "未知"}
        </time>
      ) : (
        <>
          <PaperLikeButton paperId={hit.id} />
          <PaperCollectorCount paperId={hit.id} />
          <CollectionPicker paperId={hit.id} />
          <Link
            href={paperHref(hit.id, { mode: "create", source: returnTo, graph: true })}
            onClick={trackSearchClick}
            aria-label="关系图谱"
            title="关系图谱"
            // 窄卡片放不下一行操作；详情页顶栏同样提供图谱入口。
            className="hidden @min-[400px]:inline-flex"
          >
            <Button size="sm" variant="outline" className="size-9 rounded-lg p-0">
              <Network className="size-4" />
            </Button>
          </Link>
          <Link href={detailHref} onClick={trackSearchClick}>
            <Button size="sm" className="h-9 rounded-lg px-4 text-[13px]">
              论文详情
              <ArrowRight className="size-3.5" />
            </Button>
          </Link>
        </>
      )}
    />
  );
}

function formatLastViewedAt(value: string) {
  const viewedAt = new Date(value);
  if (Number.isNaN(viewedAt.getTime())) return value;
  const elapsedMinutes = Math.floor((Date.now() - viewedAt.getTime()) / 60000);
  if (elapsedMinutes < 60) return `${Math.max(1, elapsedMinutes)}分钟前`;
  if (elapsedMinutes < 1440) return `${Math.floor(elapsedMinutes / 60)}小时前`;
  if (elapsedMinutes < 10080) return `${Math.floor(elapsedMinutes / 1440)}天前`;
  return viewedAt.toLocaleString("zh-CN", { hour12: false });
}
