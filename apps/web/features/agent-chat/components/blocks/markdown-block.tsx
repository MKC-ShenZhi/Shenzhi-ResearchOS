"use client";

import { useMemo } from "react";
import type { MarkdownBlock as MarkdownBlockData, Reference } from "../../../../clients/backend/agent-message";
import { StreamdownRenderer } from "../streamdown-renderer";
import { citationTargets } from "../message-presentation";

export function MarkdownBlock({ block, references, anchorPrefix, isStreaming = false }: {
  block: MarkdownBlockData; references: readonly Reference[]; anchorPrefix: string; isStreaming?: boolean;
}) {
  const citations = useMemo(() => citationTargets(references, anchorPrefix), [references, anchorPrefix]);
  return <StreamdownRenderer content={block.content} citations={citations} isStreaming={isStreaming} />;
}
