"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UserPreferencesState {
  /** 已关注的学者 id 集合 */
  followedScholars: Record<string, boolean>;
  /** 已收藏的机构 id 集合 */
  bookmarkedInstitutions: Record<string, boolean>;
  toggleFollow: (scholarId: string, defaultFollowing?: boolean) => void;
  toggleInstitutionBookmark: (
    institutionId: string,
    defaultBookmarked?: boolean,
  ) => void;
}

const CURRENT_VERSION = 2;

/**
 * 浏览器本地偏好只保留界面级状态。
 *
 * 论文收藏、论文点赞和主题关注都由服务端账号数据承载：本地不再保存
 * followedTopics / likedPapers / bookmarkedPapers，也不把历史本地值导入账号。
 */
export const useUserPreferences = create<UserPreferencesState>()(
  persist(
    (set) => ({
      followedScholars: { "yoshua-bengio": true, "pieter-abbeel": true },
      bookmarkedInstitutions: {},
      toggleFollow: (scholarId, defaultFollowing = false) =>
        set((s) => ({
          followedScholars: {
            ...s.followedScholars,
            [scholarId]: !(s.followedScholars[scholarId] ?? defaultFollowing),
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
    {
      name: "shenzhi-user-preferences",
      version: CURRENT_VERSION,
      // v1 stored topic follows, paper likes and paper bookmarks in the browser.
      // All three are server-owned now, so stale values are dropped rather than
      // silently imported into the signed-in account.
      migrate: (persisted, version) => {
        const state = (persisted ?? {}) as Record<string, unknown>;
        if (version < 2) {
          delete state.followedTopics;
          delete state.likedPapers;
          delete state.bookmarkedPapers;
        }
        return state as unknown as UserPreferencesState;
      },
    },
  ),
);
