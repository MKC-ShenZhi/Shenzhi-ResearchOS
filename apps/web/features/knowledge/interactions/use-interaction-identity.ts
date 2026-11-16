"use client";

import { useAuth } from "@/components/auth/auth-provider";

/**
 * 互动状态的身份键。
 *
 * 匿名使用空字符串，登录使用 Better Auth 用户 ID。会话解析完成前不发起
 * 请求，避免把匿名（无个人状态）的结果写进登录账号的缓存键。
 */
export function useInteractionIdentity() {
  const { session, isPending } = useAuth();
  const userId = session?.user?.id ?? "";
  return {
    identityKey: userId,
    isSessionPending: isPending,
    isAuthenticated: Boolean(userId),
  };
}
