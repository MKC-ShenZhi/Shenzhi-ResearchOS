"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchPaperInteraction,
  paperInteractionQueryKey,
  type PaperInteraction,
} from "@/clients/backend/interactions";
import { useInteractionIdentity } from "./use-interaction-identity";

/** 单篇论文的收藏人数、点赞人数与当前身份状态（同一事件循环内的卡片自动合批）。 */
export function usePaperInteraction(paperId: string, enabled = true) {
  const { identityKey, isSessionPending } = useInteractionIdentity();
  const query = useQuery<PaperInteraction>({
    queryKey: paperInteractionQueryKey(identityKey, paperId),
    queryFn: () => fetchPaperInteraction(identityKey, paperId),
    enabled: enabled && !isSessionPending && Boolean(paperId),
    staleTime: 60_000,
    retry: false,
  });
  return {
    interaction: query.data ?? null,
    isResolving: isSessionPending || (Boolean(paperId) && query.isPending),
    isError: query.isError,
    refetch: query.refetch,
  };
}
