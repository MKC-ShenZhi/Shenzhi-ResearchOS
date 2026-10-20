"use client";

import { useState } from "react";
import { ThumbsUp } from "lucide-react";
import { ApiError } from "@/clients/backend/http";
import { useAuth } from "@/components/auth/auth-provider";
import { usePaperInteraction } from "../use-paper-interaction";
import { usePaperLike } from "../use-paper-like";

/**
 * 论文点赞按钮。
 *
 * 未登录时只弹出既有登录窗口，不代替用户完成点赞；登录后由用户再次点击。
 * 按钮样式沿用卡片原来的点赞样式，请求进行中禁止重复提交。
 */
export function PaperLikeButton({
  paperId,
  className = "",
}: {
  paperId: string;
  className?: string;
}) {
  const { session, isPending: isAuthPending, openLogin } = useAuth();
  const { interaction, isResolving, isError, refetch } = usePaperInteraction(paperId);
  const { toggle, isSaving } = usePaperLike(paperId);
  const [error, setError] = useState("");
  const liked = interaction?.liked === true;
  const count = interaction?.likeCount;
  const stateUnavailable = Boolean(session) && isError && !interaction;

  async function handleClick() {
    if (isAuthPending || isSaving) return;
    if (!session) {
      openLogin({ notice: "登录后即可点赞论文" });
      return;
    }
    if (interaction?.liked === null || interaction?.liked === undefined) {
      const result = await refetch();
      setError(result.isError ? "点赞状态加载失败，请重试" : "");
      return;
    }
    setError("");
    try {
      await toggle(liked);
    } catch (error) {
      // 会话在此期间失效时重新走登录窗口，而不是静默失败。
      if (error instanceof ApiError && error.status === 401) {
        openLogin({ notice: "登录状态已失效，请重新登录" });
        return;
      }
      setError("操作失败，请重试");
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => void handleClick()}
        aria-pressed={liked}
        aria-label={stateUnavailable ? "重试加载点赞状态" : liked ? "取消点赞" : "点赞"}
        title={stateUnavailable ? "重试加载点赞状态" : liked ? "取消点赞" : "点赞"}
        disabled={isAuthPending || isSaving || (Boolean(session) && isResolving)}
        className={
          "flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] transition-colors disabled:cursor-progress disabled:opacity-60 " +
          (liked ? "text-primary" : "text-muted hover:bg-chip") +
          (className ? ` ${className}` : "")
        }
      >
        <ThumbsUp className="size-4" fill={liked ? "currentColor" : "none"} />
        {count !== undefined && count.toLocaleString()}
      </button>
      {(error || stateUnavailable) && <span role="alert" className="text-[11px] text-danger">{error || "点赞状态加载失败"}</span>}
    </>
  );
}
