"use client";

import { useEffect, useState } from "react";
import { Loader2, ThumbsDown, ThumbsUp } from "lucide-react";
import type { AgentMessage } from "../../../clients/backend/agent-message";
import { Button } from "../../../components/ui/button";
import { MessageCopyButton } from "./message-copy-button";
import { canShowMessageActions, messageCopyText, toggleFeedback, type MessageFeedback } from "./message-actions-state";

export function MessageActions({ message, content, status, isStreaming }: {
  message: AgentMessage | null; content: string; status?: string; isStreaming: boolean;
}) {
  const [feedback, setFeedback] = useState<MessageFeedback>(null);
  const [notice, setNotice] = useState("");
  const [pendingFeedback, setPendingFeedback] = useState<Exclude<MessageFeedback, null> | null>(null);
  useEffect(() => {
    if (!pendingFeedback) return;
    // Short local transition; no feedback request is sent.
    const timer = setTimeout(() => {
      const next = toggleFeedback(feedback, pendingFeedback);
      setFeedback(next);
      setNotice(next === null ? "已取消反馈" : next === "like" ? "感谢你的认可" : "感谢你的反馈");
      setPendingFeedback(null);
    }, 450);
    return () => clearTimeout(timer);
  }, [pendingFeedback, feedback]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 2500);
    return () => clearTimeout(timer);
  }, [notice]);

  const text = messageCopyText(message, content);
  if (!canShowMessageActions(message, status, isStreaming, text)) return null;

  return (
    <div role="group" aria-label="AI 回复操作" className="mt-3 flex flex-wrap items-center gap-1 text-muted">
      <MessageCopyButton text={text} />
      {/* 反馈目前仅为前端交互占位，后续可接入真实反馈接口。 */}
      {(["like", "dislike"] as const).map((value) => {
        const Icon = value === "like" ? ThumbsUp : ThumbsDown;
        const label = value === "like" ? "点赞" : "点踩";
        const selected = feedback === value;
        return <Button key={value} type="button" variant="ghost" size="icon"
          className={selected ? "bg-primary-soft text-primary" : "text-muted"}
          title={selected ? `取消${label}` : label} aria-label={label} aria-pressed={selected}
          disabled={pendingFeedback !== null} aria-busy={pendingFeedback === value}
          onClick={() => {
            setNotice("");
            setPendingFeedback(value);
          }}>
          {pendingFeedback === value ? <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
            : <Icon aria-hidden="true" fill={selected ? "currentColor" : "none"} />}
        </Button>;
      })}
      <span role="status" aria-live="polite" className="text-xs">{notice}</span>
    </div>
  );
}
