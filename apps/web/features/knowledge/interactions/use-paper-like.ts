"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  likePaper,
  paperInteractionQueryKey,
  publishPaperInteraction,
  unlikePaper,
  type LikeState,
  type PaperInteraction,
} from "@/clients/backend/interactions";
import { useInteractionIdentity } from "./use-interaction-identity";

/**
 * 点赞/取消点赞只接受服务端结果：没有乐观写入，因此失败时界面显示的仍是
 * 上一次真实状态，不需要回滚。成功后写入当前身份缓存并广播到其他标签页。
 */
export function usePaperLike(paperId: string) {
  const { identityKey, isAuthenticated } = useInteractionIdentity();
  const queryClient = useQueryClient();
  const mutation = useMutation<LikeState, unknown, boolean>({
    mutationFn: (liked) => (liked ? unlikePaper(paperId) : likePaper(paperId)),
    onSuccess: (state) => {
      if (!isAuthenticated || !identityKey) return;
      queryClient.setQueryData<PaperInteraction | undefined>(
        paperInteractionQueryKey(identityKey, paperId),
        (current) => current
          ? { ...current, liked: state.liked, likeCount: state.likeCount }
          : current,
      );
      publishPaperInteraction(identityKey, {
        paperId,
        liked: state.liked,
        likeCount: state.likeCount,
      });
    },
  });
  return {
    toggle: (currentlyLiked: boolean) => mutation.mutateAsync(currentlyLiked),
    isSaving: mutation.isPending,
  };
}
