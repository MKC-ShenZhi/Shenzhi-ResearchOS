"use client";

import { useState } from "react";
import { Check, Plus } from "lucide-react";
import { ApiError } from "@/clients/backend/http";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { useTopicInteraction } from "../use-topic-interaction";
import { useTopicFollow } from "../use-topic-follow";

/**
 * 主题关注按钮。
 *
 * 未登录时只弹出既有登录窗口；已登录时写入服务端并以返回的人数为准。
 * 请求进行中禁止重复提交。
 */
export function TopicFollowButton({
  topicId,
  className = "",
}: {
  topicId: string;
  className?: string;
}) {
  const { session, isPending: isAuthPending, openLogin } = useAuth();
  const { interaction, isResolving, isError, refetch } = useTopicInteraction(topicId);
  const { toggle, isSaving } = useTopicFollow(topicId);
  const [error, setError] = useState("");
  const following = interaction?.isFollowing === true;
  const stateUnavailable = Boolean(session) && isError && !interaction;

  async function handleClick() {
    if (isAuthPending || isSaving) return;
    if (!session) {
      openLogin({ notice: "登录后即可关注主题" });
      return;
    }
    if (interaction?.isFollowing === null || interaction?.isFollowing === undefined) {
      const result = await refetch();
      if (result.isError) setError("关注状态加载失败，请重试");
      else setError("");
      return;
    }
    setError("");
    try {
      await toggle(following);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        openLogin({ notice: "登录状态已失效，请重新登录" });
        return;
      }
      setError("操作失败，请重试");
    }
  }

  return (
    <>
      <Button
        type="button"
        variant={following ? "soft" : "default"}
        size="sm"
        aria-pressed={following}
        aria-label={stateUnavailable ? "重试加载关注状态" : following ? "取消关注主题" : "关注主题"}
        title={stateUnavailable ? "重试加载关注状态" : following ? "取消关注主题" : "关注主题"}
        disabled={isAuthPending || isSaving || (Boolean(session) && isResolving)}
        onClick={() => void handleClick()}
        className={className || undefined}
      >
        {following ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}
        {stateUnavailable ? "重试" : Boolean(session) && isResolving ? "加载中" : following ? "已关注" : "关注"}
      </Button>
      {(error || stateUnavailable) && <span role="alert" className="text-[11px] text-danger">{error || "关注状态加载失败"}</span>}
    </>
  );
}
