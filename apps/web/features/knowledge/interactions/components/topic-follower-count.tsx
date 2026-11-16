"use client";

import { Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTopicInteraction } from "../use-topic-interaction";

/**
 * 主题的真实关注人数（distinct 用户）。
 * 目录里的 followersCount 只是历史快照，不再作为人数来源。
 */
export function TopicFollowerCount({
  topicId,
  className,
}: {
  topicId: string;
  className?: string;
}) {
  const { interaction, isError } = useTopicInteraction(topicId);
  const count = interaction?.followerCount;
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-xs text-muted", className)}
      title="关注人数"
    >
      <Users className="size-3.5" />
      {isError && count === undefined ? "人数暂不可用" : `${count === undefined ? "…" : count.toLocaleString()} 人关注`}
    </span>
  );
}
