"use client";

import { useId } from "react";
import type { AgentMessage } from "../../../clients/backend/agent-message";
import { BlockRenderer } from "./block-renderer";
import { ReferencesRenderer } from "./references-renderer";
import { messageTime, MESSAGE_STATUS } from "./message-presentation";

export function MessageRenderer({ message, activeBlockId = null, isStreaming = false }: {
  message: AgentMessage; activeBlockId?: string | null; isStreaming?: boolean;
}) {
  const anchorPrefix = `agent-message-${useId().replace(/[^a-zA-Z0-9_-]/g, "_")}`;
  const time = messageTime(message.created_at);
  return (
    <article aria-label="AI 回复" className="min-w-0 rounded-2xl border border-line bg-card px-4 py-3 sm:px-5 sm:py-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {time && <time dateTime={time.dateTime}>{time.label}</time>}
        <span role="status" aria-live="polite">{MESSAGE_STATUS[message.status]}</span>
      </div>
      <div className="space-y-3">
        {message.blocks.map((block) => <BlockRenderer key={block.id} block={block}
          references={message.references} anchorPrefix={anchorPrefix}
          isStreaming={isStreaming && message.status === "running" && activeBlockId === block.id} />)}
      </div>
      <ReferencesRenderer references={message.references} anchorPrefix={anchorPrefix} />
    </article>
  );
}
