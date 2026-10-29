"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { likePaper, publishPaperInteraction, unlikePaper } from "@/clients/backend/interactions";
import { useCollections } from "@/stores/collections";
import { refreshPaperQueries } from "./cache";
import { useInteractionIdentity } from "./use-interaction-identity";

/** Keep the mutation's owner, even if React rerenders under another account. */
export function usePaperLike(paperId: string) {
  const { identityKey } = useInteractionIdentity();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ liked, userId }: { liked: boolean; userId: string; generation: number }) =>
      liked ? unlikePaper(paperId, userId) : likePaper(paperId, userId),
    onSuccess: async (state, { userId, generation }) => {
      const current = useCollections.getState();
      if (current.identityKey !== userId || current.generation !== generation) return;
      await refreshPaperQueries(queryClient, userId, paperId);
      publishPaperInteraction(userId, state);
    },
  });
  return {
    toggle: (liked: boolean) => {
      const { identityKey: current, generation } = useCollections.getState();
      if (!identityKey || current !== identityKey) return Promise.reject(new Error("账号已切换"));
      return mutation.mutateAsync({ liked, userId: identityKey, generation });
    },
    isSaving: mutation.isPending,
  };
}
