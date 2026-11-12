"use client";

import type { ComponentProps, ReactNode, Ref } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Users } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { ExpandableAbstract } from "@/components/common/expandable-abstract";
import { PaperThumbnail } from "@/components/common/paper-thumbnail";
import { PAPER_CARD_INTERACTION_CLASS, usePaperCardNavigation } from "@/components/common/use-paper-card-navigation";
import { Badge } from "@/components/ui/badge";
import { PaperReadBadge } from "@/features/knowledge/papers/components/paper-read-badge";
import { usePaperReadStatus } from "@/features/knowledge/papers/use-paper-read-status";
import { topicHref } from "@/features/knowledge/topics/topic-url-state";
import type { PaperCardModel } from "@/types";

/**
 * 首页、检索和学者成果共用的论文卡片版式。数据转换、埋点与底部操作由各场景自己提供：
 * `onNavigate` 在进入详情前触发，`actions` 放在底部右侧。
 */
export function PaperCardLayout({
  paper,
  index,
  detailHref = "",
  onNavigate,
  behaviorSource,
  actions,
  articleRef,
  deferOffscreen = false,
}: {
  paper: PaperCardModel;
  index: number;
  detailHref?: string;
  onNavigate?: () => void;
  behaviorSource?: ComponentProps<typeof ExpandableAbstract>["source"];
  actions: ReactNode;
  articleRef?: Ref<HTMLElement>;
  /** 长列表中跳过屏幕外卡片的渲染。 */
  deferOffscreen?: boolean;
}) {
  const { session } = useAuth();
  const userId = detailHref ? session?.user.id ?? "" : "";
  const status = usePaperReadStatus(paper.id, Boolean(detailHref));
  const cardNavigation = usePaperCardNavigation(detailHref, paper.title, onNavigate);

  return (
    <motion.article
      ref={articleRef}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: (index % 12) * 0.03 }}
      className={`@container relative rounded-2xl bg-card p-6 shadow-card [overflow-wrap:anywhere] has-[[data-collection-picker-open]]:z-40 ${deferOffscreen ? "[contain-intrinsic-size:auto_260px] [content-visibility:auto] has-[[data-collection-picker-open]]:[content-visibility:visible]" : ""} ${detailHref ? PAPER_CARD_INTERACTION_CLASS : ""}`}
      {...(detailHref ? cardNavigation : {})}
    >
      <div className="grid grid-cols-1 items-start gap-x-6 gap-y-4 @min-[600px]:grid-cols-[minmax(0,1fr)_clamp(200px,30cqw,280px)]">
        <div className="min-w-0">
          {/* 元信息行 */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
            <span className="text-faint">{paper.date}</span>
            {paper.venue && <Badge variant={paper.venueTone}>{paper.venue}</Badge>}
            {status && <PaperReadBadge status={status} />}
            <span className="flex min-w-0 items-center gap-1.5 text-muted">
              <Users className="size-3.5 shrink-0 text-faint" />
              <span className="min-w-0">{paper.authors}</span>
            </span>
          </div>

          {/* 标题 */}
          <h3 title={paper.title} className="mt-2 line-clamp-2 text-[17px] font-bold leading-snug text-ink">
            {detailHref ? (
              <Link href={detailHref} onClick={onNavigate} className="transition-colors hover:text-primary">
                {paper.title}
              </Link>
            ) : paper.title}
          </h3>
          {/* 摘要 */}
          <ExpandableAbstract
            abstract={paper.abstract}
            paperId={paper.id}
            source={behaviorSource}
            userId={userId}
            className="mt-3 text-sm leading-relaxed text-muted"
            collapsedClassName="line-clamp-4"
          />
        </div>

        {/* 单栏时占位图只会拉高卡片，仅展示真实图片 */}
        <div className={`w-full max-w-[280px] justify-self-center self-start ${paper.thumbnailUrl ? "" : "hidden @min-[600px]:block"}`}>
          <PaperThumbnail src={paper.thumbnailUrl} title={paper.title} eager={index < 2} aspectRatio={7 / 5} />
        </div>

        {/* 底部：Topic + 操作 */}
        <div className="col-span-full flex flex-wrap items-center justify-between gap-3">
          {paper.topics.length > 0 && (
            <div className="flex min-w-0 flex-1 basis-48 flex-wrap gap-x-4 gap-y-1">
              {paper.topics.map((topic) => {
                const name = topic.nameZh || topic.nameEn;
                return (
                  <Link
                    key={topic.id}
                    href={topicHref(topic.id)}
                    prefetch={false}
                    title={name}
                    className="max-w-full truncate rounded-sm text-[13px] leading-5 text-muted hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-primary"
                  >
                    #{name}
                  </Link>
                );
              })}
            </div>
          )}
          <div className="ml-auto flex max-w-full flex-wrap items-center justify-end gap-2">
            {actions}
          </div>
        </div>
      </div>
    </motion.article>
  );
}
