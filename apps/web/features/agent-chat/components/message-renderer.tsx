"use client";

import { useId, useMemo } from "react";
import type { AgentMessage } from "../../../clients/backend/agent-message";
import { BlockRenderer } from "./block-renderer";
import { ReferencesRenderer } from "./references-renderer";
import { citationTargets, citedReferenceIds, messageTime, MESSAGE_STATUS } from "./message-presentation";

export function MessageRenderer({ message, activeBlockId = null, isStreaming = false }: {
  message: AgentMessage; activeBlockId?: string | null; isStreaming?: boolean;
}) {
  const anchorPrefix = `agent-message-${useId().replace(/[^a-zA-Z0-9_-]/g, "_")}`;
  const time = messageTime(message.created_at);
  const { citations, references } = useMemo(() => {
    const ids = citedReferenceIds(message.blocks);
    const sources = new Map(message.references.map((reference) => [reference.id, reference]));
    return { citations: citationTargets(message.references, anchorPrefix, ids, message.status === "running"),
      references: ids.flatMap((id) => sources.has(id) ? [sources.get(id)!] : []) };
  }, [message.blocks, message.references, message.status, anchorPrefix]);
  return (
    <article aria-label="AI 回复" className="min-w-0 rounded-2xl border border-line bg-card px-4 py-3 sm:px-5 sm:py-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {time && <time dateTime={time.dateTime}>{time.label}</time>}
        <span role="status" aria-live="polite">{MESSAGE_STATUS[message.status]}</span>
      </div>
      <div className="space-y-3">
        {message.blocks.map((block) => <BlockRenderer key={block.id} block={block}
          citations={citations}
          isStreaming={isStreaming && message.status === "running" && activeBlockId === block.id} />)}
      </div>
      <ReferencesRenderer references={references} anchorPrefix={anchorPrefix} citations={citations} />
    </article>
  );
}
