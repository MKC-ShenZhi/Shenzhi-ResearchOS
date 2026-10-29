"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { followTopic, publishTopicInteraction, unfollowTopic } from "@/clients/backend/interactions";
import { useCollections } from "@/stores/collections";
import { refreshTopicQueries } from "./cache";
import { useInteractionIdentity } from "./use-interaction-identity";

export function useTopicFollow(topicId: string) {
  const { identityKey } = useInteractionIdentity();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ following, userId }: { following: boolean; userId: string; generation: number }) =>
      following ? unfollowTopic(topicId, userId) : followTopic(topicId, userId),
    onSuccess: async (state, { userId, generation }) => {
      const current = useCollections.getState();
      if (current.identityKey !== userId || current.generation !== generation) return;
      await refreshTopicQueries(queryClient, userId, topicId);
      publishTopicInteraction(userId, state);
    },
  });
  return {
    toggle: (following: boolean) => {
      const { identityKey: current, generation } = useCollections.getState();
      if (!identityKey || current !== identityKey) return Promise.reject(new Error("账号已切换"));
      return mutation.mutateAsync({ following, userId: identityKey, generation });
    },
    isSaving: mutation.isPending,
  };
}
