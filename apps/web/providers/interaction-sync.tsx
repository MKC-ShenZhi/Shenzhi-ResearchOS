"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/auth-provider";
import {
  PAPER_INTERACTION_CHANNEL,
  TOPIC_INTERACTION_CHANNEL,
  paperInteractionQueryKey,
  topicInteractionQueryKey,
  type PaperInteraction,
  type TopicInteraction,
} from "@/clients/backend/interactions";

const INTERACTION_QUERY_KINDS = new Set(["paper-interaction", "topic-interaction"]);

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? value as Record<string, unknown> : null;
}

/**
 * 个人互动状态的身份隔离与跨标签页同步。
 *
 * - 账号切换或退出后，其他身份的个人状态缓存被移除；匿名键只含公开人数，保留。
 * - 同一账号在另一个标签页点赞/关注后，本页卡片随广播更新。
 */
export function InteractionSync() {
  const { session } = useAuth();
  const userId = session?.user?.id ?? "";
  const queryClient = useQueryClient();
  const previousUserId = useRef<string | null>(null);

  useEffect(() => {
    const previous = previousUserId.current;
    previousUserId.current = userId;
    if (previous === null || previous === userId) return;
    queryClient.removeQueries({
      predicate: (query) => {
        if (!INTERACTION_QUERY_KINDS.has(String(query.queryKey[0]))) return false;
        const owner = query.queryKey[1];
        return typeof owner === "string" && owner !== "" && owner !== userId;
      },
    });
  }, [queryClient, userId]);

  useEffect(() => {
    if (!userId || typeof BroadcastChannel === "undefined") return;

    const paperChannel = new BroadcastChannel(PAPER_INTERACTION_CHANNEL);
    paperChannel.onmessage = (event: MessageEvent<unknown>) => {
      const message = asRecord(event.data);
      if (!message || message.userId !== userId || typeof message.paperId !== "string") return;
      queryClient.setQueryData<PaperInteraction | undefined>(
        paperInteractionQueryKey(userId, message.paperId),
        (current) => current ? {
          ...current,
          liked: typeof message.liked === "boolean" ? message.liked : current.liked,
          likeCount: typeof message.likeCount === "number" ? message.likeCount : current.likeCount,
          collectorCount: typeof message.collectorCount === "number"
            ? message.collectorCount
            : current.collectorCount,
        } : current,
      );
    };

    const topicChannel = new BroadcastChannel(TOPIC_INTERACTION_CHANNEL);
    topicChannel.onmessage = (event: MessageEvent<unknown>) => {
      const message = asRecord(event.data);
      if (!message || message.userId !== userId || typeof message.topicId !== "string") return;
      queryClient.setQueryData<TopicInteraction | undefined>(
        topicInteractionQueryKey(userId, message.topicId),
        (current) => current ? {
          ...current,
          isFollowing: typeof message.isFollowing === "boolean"
            ? message.isFollowing
            : current.isFollowing,
          followerCount: typeof message.followerCount === "number"
            ? message.followerCount
            : current.followerCount,
        } : current,
      );
    };

    return () => {
      paperChannel.close();
      topicChannel.close();
    };
  }, [queryClient, userId]);

  return null;
}
