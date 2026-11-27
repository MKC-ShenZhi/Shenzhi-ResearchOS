"use client";

import { useEffect, useState } from "react";
import { Copy, ThumbsDown, ThumbsUp } from "lucide-react";
import type { AgentMessage } from "../../../clients/backend/agent-message";
import { Button } from "../../../components/ui/button";
import { canShowMessageActions, messageCopyText, toggleFeedback, type MessageFeedback } from "./message-actions-state";

export function MessageActions({ message, content, status, isStreaming }: {
  message: AgentMessage | null; content: string; status?: string; isStreaming: boolean;
}) {
  const [feedback, setFeedback] = useState<MessageFeedback>(null);
  const [notice, setNotice] = useState("");
  const [copying, setCopying] = useState(false);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 2500);
    return () => clearTimeout(timer);
  }, [notice]);

  const text = messageCopyText(message, content);
  if (!canShowMessageActions(message, status, isStreaming, text)) return null;

  async function copy() {
    setCopying(true);
    setNotice("");
    try {
      await navigator.clipboard.writeText(text);
      setNotice("已复制");
    } catch {
      setNotice("复制失败，请重试或手动复制");
    } finally {
      setCopying(false);
    }
  }

  return (
    <div role="group" aria-label="AI 回复操作" className="mt-3 flex flex-wrap items-center gap-1 text-muted">
      <Button type="button" variant="ghost" size="icon" className="text-muted" title="复制回复" aria-label="复制回复" disabled={copying} onClick={copy}>
        <Copy aria-hidden="true" />
      </Button>
      {/* 反馈目前仅为前端交互占位，后续可接入真实反馈接口。 */}
      {(["like", "dislike"] as const).map((value) => {
        const Icon = value === "like" ? ThumbsUp : ThumbsDown;
        const label = value === "like" ? "点赞" : "点踩";
        const selected = feedback === value;
        return <Button key={value} type="button" variant="ghost" size="icon"
          className={selected ? "bg-primary-soft text-primary" : "text-muted"}
          title={selected ? `取消${label}` : label} aria-label={label} aria-pressed={selected}
          onClick={() => {
            setFeedback((current) => toggleFeedback(current, value));
            setNotice(selected ? "已取消反馈" : value === "like" ? "感谢你的认可" : "感谢你的反馈");
          }}>
          <Icon aria-hidden="true" fill={selected ? "currentColor" : "none"} />
        </Button>;
      })}
      <span role="status" aria-live="polite" className="text-xs">{notice}</span>
    </div>
  );
}
