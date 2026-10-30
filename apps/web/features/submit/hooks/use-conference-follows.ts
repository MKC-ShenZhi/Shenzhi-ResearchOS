"use client";

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/auth-provider";
import {
  conferenceQueryRetry,
  fetchConferenceDeadlines,
  followConference,
  unfollowConference,
  type ConferenceDeadlineDto,
  type ConferenceDeadlineListDto,
} from "@/clients/backend/conferences";

/** 关注列表按账号隔离缓存，切换账号不会串用上一个账号的数据 */
export const followedConferencesQueryKey = (userId: string) => ["conference-follows", userId] as const;

/** 「只看关注」的会议列表同样按账号区分；失效时按此前缀刷新 */
export const followedDeadlinesQueryPrefix = (userId: string) => ["conference-deadlines", userId] as const;

/**
 * 当前账号关注的会议（含已截止）。投稿页置顶区、卡片关注状态和侧边栏截稿提醒共用这一份数据。
 */
export function useFollowedConferences() {
  const { session, isPending } = useAuth();
  const userId = session?.user?.id ?? "";
  const query = useQuery({
    queryKey: followedConferencesQueryKey(userId),
    queryFn: ({ signal }) => fetchConferenceDeadlines({ followed: true }, signal),
    enabled: Boolean(userId) && !isPending,
    staleTime: 5 * 60 * 1000,
    retry: conferenceQueryRetry,
  });
  const items = query.data?.items;
  const ids = useMemo(() => new Set((items ?? []).map((item) => item.id)), [items]);
  return {
    userId,
    items: items ?? [],
    ids,
    isResolving: Boolean(userId) && query.isPending,
  };
}

/** 关注 / 取消关注：先乐观更新关注列表，失败回滚，完成后以服务端结果为准 */
export function useConferenceFollowToggle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conference, following, userId }: {
      conference: ConferenceDeadlineDto;
      following: boolean;
      userId: string;
    }) => (following ? unfollowConference(conference.id, userId) : followConference(conference.id, userId)),
    onMutate: async ({ conference, following, userId }) => {
      const key = followedConferencesQueryKey(userId);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<ConferenceDeadlineListDto>(key);
      if (previous) {
        const items = following
          ? previous.items.filter((item) => item.id !== conference.id)
          : [...previous.items.filter((item) => item.id !== conference.id), conference];
        queryClient.setQueryData<ConferenceDeadlineListDto>(key, { ...previous, items, total: items.length });
      }
      return { previous };
    },
    onError: (_error, { userId }, context) => {
      if (context?.previous) queryClient.setQueryData(followedConferencesQueryKey(userId), context.previous);
    },
    onSettled: (_data, _error, { userId }) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: followedConferencesQueryKey(userId) }),
        queryClient.invalidateQueries({ queryKey: followedDeadlinesQueryPrefix(userId) }),
      ]),
  });
}
