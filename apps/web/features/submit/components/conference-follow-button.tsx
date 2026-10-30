"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, BellRing } from "lucide-react";
import { ApiError } from "@/clients/backend/http";
import type { ConferenceDeadlineDto } from "@/clients/backend/conferences";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { useConferenceFollowToggle } from "@/features/submit/hooks/use-conference-follows";

/**
 * 关注截稿 —— 关注后会议置顶在投稿页，临近截稿时侧边栏提醒，用户留在站内跟踪倒计时。
 * 未登录时只弹出既有登录窗口。
 */
export function ConferenceFollowButton({
  conference,
  following,
  resolving,
}: {
  conference: ConferenceDeadlineDto;
  following: boolean;
  resolving: boolean;
}) {
  const { session, isPending: isAuthPending, openLogin } = useAuth();
  const toggle = useConferenceFollowToggle();
  const [error, setError] = useState("");
  const userId = session?.user?.id;

  async function handleClick() {
    if (isAuthPending || toggle.isPending) return;
    if (!userId) {
      openLogin({ notice: "登录后即可关注会议，在深知跟踪截稿倒计时" });
      return;
    }
    setError("");
    try {
      await toggle.mutateAsync({ conference, following, userId });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        openLogin({ notice: "登录状态已失效，请重新登录" });
        return;
      }
      setError("操作失败，请重试");
    }
  }

  return (
    <>
      <Button
        variant={following ? "soft" : "default"}
        size="sm"
        aria-pressed={following}
        disabled={isAuthPending || resolving}
        onClick={() => void handleClick()}
      >
        <AnimatePresence initial={false} mode="popLayout">
          <motion.span
            key={following ? "on" : "off"}
            initial={{ scale: 0.4, rotate: -30, opacity: 0 }}
            animate={{ scale: 1, rotate: 0, opacity: 1 }}
            exit={{ scale: 0.4, opacity: 0 }}
            transition={{ type: "spring", stiffness: 500, damping: 22 }}
            className="flex"
          >
            {following ? <BellRing /> : <Bell />}
          </motion.span>
        </AnimatePresence>
        {following ? "已关注" : "关注截稿"}
      </Button>
      {error && <span role="alert" className="text-xs text-danger">{error}</span>}
    </>
  );
}
