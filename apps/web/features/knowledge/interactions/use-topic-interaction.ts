"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchTopicInteraction,
  topicInteractionQueryKey,
  type TopicInteraction,
} from "@/clients/backend/interactions";
import { useInteractionIdentity } from "./use-interaction-identity";

/** 单个主题的关注人数与当前身份状态（同一事件循环内的卡片自动合批）。 */
export function useTopicInteraction(topicId: string, enabled = true) {
  const { identityKey, isSessionPending } = useInteractionIdentity();
  const query = useQuery<TopicInteraction>({
    queryKey: topicInteractionQueryKey(identityKey, topicId),
    queryFn: () => fetchTopicInteraction(identityKey, topicId),
    enabled: enabled && !isSessionPending && Boolean(topicId),
    staleTime: 60_000,
    retry: false,
  });
  return {
    interaction: isSessionPending ? null : query.data ?? null,
    isResolving: isSessionPending || (Boolean(topicId) && query.isPending),
    isError: query.isError,
    refetch: query.refetch,
  };
}
