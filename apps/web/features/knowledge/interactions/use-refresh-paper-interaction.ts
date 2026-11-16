"use client";

import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { publishCollectionChange } from "@/clients/backend/interactions";
import { useCollections } from "@/stores/collections";
import { refreshCollectionQueries } from "./cache";
import { useInteractionIdentity } from "./use-interaction-identity";

/** Re-read facts after a collection write; never infer a count from folder rows. */
export function useRefreshPaperInteraction(paperId?: string) {
  const { identityKey } = useInteractionIdentity();
  const queryClient = useQueryClient();
  return useCallback(async () => {
    if (!identityKey || useCollections.getState().identityKey !== identityKey) return;
    publishCollectionChange(identityKey, paperId);
    await refreshCollectionQueries(queryClient, identityKey, paperId);
  }, [identityKey, paperId, queryClient]);
}
