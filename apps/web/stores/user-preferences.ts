"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UserPreferencesState {
  /** 已关注的学者 id 集合 */
  followedScholars: Record<string, boolean>;
  /** 已关注的主题 id 集合；登录关注接口接入后可由服务端状态覆盖 */
  followedTopics: Record<string, boolean>;
  /** 已点赞的论文 id 集合 */
  likedPapers: Record<string, boolean>;
  /** 已收藏的论文 id 集合 */
  bookmarkedPapers: Record<string, boolean>;
  /** 已收藏的机构 id 集合 */
  bookmarkedInstitutions: Record<string, boolean>;
  toggleFollow: (scholarId: string, defaultFollowing?: boolean) => void;
  toggleTopicFollow: (topicId: string, defaultFollowing?: boolean) => void;
  toggleLike: (paperId: string) => void;
  toggleBookmark: (paperId: string) => void;
  toggleInstitutionBookmark: (
    institutionId: string,
    defaultBookmarked?: boolean,
  ) => void;
}

export const useUserPreferences = create<UserPreferencesState>()(
  persist(
    (set) => ({
      followedScholars: { "yoshua-bengio": true, "pieter-abbeel": true },
      followedTopics: {},
      likedPapers: {},
      bookmarkedPapers: {},
      bookmarkedInstitutions: {},
      toggleFollow: (scholarId, defaultFollowing = false) =>
        set((s) => ({
          followedScholars: {
            ...s.followedScholars,
            [scholarId]: !(s.followedScholars[scholarId] ?? defaultFollowing),
          },
        })),
      toggleTopicFollow: (topicId, defaultFollowing = false) =>
        set((s) => ({
          followedTopics: {
            ...s.followedTopics,
            [topicId]: !(s.followedTopics[topicId] ?? defaultFollowing),
          },
        })),
      toggleLike: (paperId) =>
        set((s) => ({
          likedPapers: { ...s.likedPapers, [paperId]: !s.likedPapers[paperId] },
        })),
      toggleBookmark: (paperId) =>
        set((s) => ({
          bookmarkedPapers: {
            ...s.bookmarkedPapers,
            [paperId]: !s.bookmarkedPapers[paperId],
          },
        })),
      toggleInstitutionBookmark: (institutionId, defaultBookmarked = false) =>
        set((s) => ({
          bookmarkedInstitutions: {
            ...s.bookmarkedInstitutions,
            [institutionId]: !(
              s.bookmarkedInstitutions[institutionId] ?? defaultBookmarked
            ),
          },
        })),
    }),
    { name: "shenzhi-user-preferences" },
  ),
);
