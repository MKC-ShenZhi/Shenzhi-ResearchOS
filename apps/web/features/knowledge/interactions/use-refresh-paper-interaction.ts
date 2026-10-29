"use client";

import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  paperInteractionQueryKey,
  publishPaperInteraction,
  type PaperInteraction,
} from "@/clients/backend/interactions";
import { useInteractionIdentity } from "./use-interaction-identity";

/**
 * 收藏写入成功后刷新同一篇论文的收藏人数。
 * 人数以服务端重新计算的结果为准，不做本地 +1/-1 推算；刷新结果再广播给其他标签页。
 */
export function useRefreshPaperInteraction(paperId: string) {
  const { identityKey, isAuthenticated } = useInteractionIdentity();
  const queryClient = useQueryClient();
  return useCallback(async () => {
    const queryKey = paperInteractionQueryKey(identityKey, paperId);
    await queryClient.invalidateQueries({ queryKey });
    if (!isAuthenticated || !identityKey) return;
    const current = queryClient.getQueryData<PaperInteraction>(queryKey);
    if (current) {
      publishPaperInteraction(identityKey, {
        paperId,
        collectorCount: current.collectorCount,
        folderIds: current.folderIds ?? [],
      });
    }
  }, [identityKey, isAuthenticated, paperId, queryClient]);
}
