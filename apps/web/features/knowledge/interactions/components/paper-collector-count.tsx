"use client";

import { Bookmark } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePaperInteraction } from "../use-paper-interaction";

/**
 * 全平台收藏用户数（按 distinct user 统计，与“文件夹内论文数”不是同一口径）。
 * 加载完成前显示占位符，不用 0 冒充真实人数。
 */
export function PaperCollectorCount({
  paperId,
  className,
  withIcon = false,
  compact = false,
}: {
  paperId: string;
  className?: string;
  withIcon?: boolean;
  compact?: boolean;
}) {
  const { interaction } = usePaperInteraction(paperId);
  const count = interaction?.collectorCount;
  const value = count === undefined ? "…" : count.toLocaleString();

  return (
    <span
      className={cn("inline-flex items-center gap-1 text-[13px] text-muted", className)}
      title="全平台收藏人数（按独立用户统计）"
    >
      {withIcon && <Bookmark className="size-4" />}
      {value}
      {compact ? null : " 人收藏"}
    </span>
  );
}
