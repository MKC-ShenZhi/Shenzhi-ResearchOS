"use client";

import Link from "next/link";
import { paperHref } from "@/lib/navigation/paper";
import { motion } from "framer-motion";
import { ArrowRight, Network, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { KnowledgePaperHit } from "@/clients/knowledge";

const VENUE_VARIANT = ["violet", "amber", "green"] as const;

function venueTone(index: number) {
  return VENUE_VARIANT[index % VENUE_VARIANT.length];
}

/** 论文搜索结果卡片 */
export function KnowledgeResultCard({
  hit,
  index,
  returnTo,
}: {
  hit: KnowledgePaperHit;
  index: number;
  returnTo: string;
}) {
  const authors = hit.authors.length ? hit.authors.join(" · ") : "未知作者";

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06 }}
      className="rounded-2xl bg-card p-6 shadow-card"
    >
      <div className="flex gap-5">
        <div className="min-w-0 flex-1">
          {/* 元信息行 */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
            <span className="text-faint">{hit.year ?? "—"}</span>
            {hit.venue ? (
              <Badge variant={venueTone(index)}>{hit.venue}</Badge>
            ) : (
              <span className="text-[11px] text-faint">暂无会议</span>
            )}
            <span className="flex min-w-0 items-center gap-1.5 text-muted">
              <Users className="size-3.5 shrink-0 text-faint" />
              <span className="truncate">{authors}</span>
            </span>
          </div>

          {/* 标题 */}
          <Link
            href={paperHref(hit.id, returnTo)}
            className="group mt-2 block"
          >
            <h3 className="text-[17px] font-bold leading-snug text-ink transition-colors group-hover:text-primary">
              {hit.title}
            </h3>
          </Link>

          {/* 摘要 */}
          {hit.abstract && (
            <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted">
              {hit.abstract}
            </p>
          )}

          {/* 底部：关键词 + 操作 */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {(hit.keywords.length ? hit.keywords : hit.subjects).slice(0, 5).map((tag) => (
                <span key={tag} className="text-[13px] text-muted">
                  #{tag}
                </span>
              ))}
              {!hit.keywords.length && !hit.subjects.length && (
                <span className="text-[11px] text-faint">暂无关键词</span>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Link href={paperHref(hit.id, returnTo)}>
                <Button size="sm" variant="outline" className="h-8 rounded-lg px-3 text-xs">
                  论文详情
                  <ArrowRight className="size-3.5" />
                </Button>
              </Link>
              <Link href={paperHref(hit.id, returnTo, true)}>
                <Button size="sm" className="h-8 rounded-lg px-3 text-xs">
                  <Network className="size-3.5" />
                  关系图谱
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {/* 右侧排序 */}
        <div className="hidden w-[104px] shrink-0 flex-col items-center justify-center rounded-xl bg-panel py-4 sm:flex">
          {hit.rank !== null ? (
            <span className="rounded-full bg-chip px-2 py-0.5 text-[10px] text-muted">
              #{hit.rank}
            </span>
          ) : (
            <p className="text-sm text-faint">—</p>
          )}
        </div>
      </div>
    </motion.article>
  );
}
