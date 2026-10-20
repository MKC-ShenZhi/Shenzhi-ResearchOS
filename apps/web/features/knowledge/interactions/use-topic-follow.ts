"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  followTopic,
  publishTopicInteraction,
  topicInteractionQueryKey,
  unfollowTopic,
  type TopicFollowState,
  type TopicInteraction,
} from "@/clients/backend/interactions";
import { useInteractionIdentity } from "./use-interaction-identity";

/** 关注/取消关注同样只写服务端结果，失败时界面保持上一次真实状态。 */
export function useTopicFollow(topicId: string) {
  const { identityKey, isAuthenticated } = useInteractionIdentity();
  const queryClient = useQueryClient();
  const mutation = useMutation<TopicFollowState, unknown, boolean>({
    mutationFn: (following) => (following ? unfollowTopic(topicId) : followTopic(topicId)),
    onSuccess: (state) => {
      if (!isAuthenticated || !identityKey) return;
      queryClient.setQueryData<TopicInteraction | undefined>(
        topicInteractionQueryKey(identityKey, topicId),
        (current) => current
          ? { ...current, isFollowing: state.isFollowing, followerCount: state.followerCount }
          : current,
      );
      publishTopicInteraction(identityKey, {
        topicId,
        isFollowing: state.isFollowing,
        followerCount: state.followerCount,
      });
    },
  });
  return {
    toggle: (currentlyFollowing: boolean) => mutation.mutateAsync(currentlyFollowing),
    isSaving: mutation.isPending,
  };
}
