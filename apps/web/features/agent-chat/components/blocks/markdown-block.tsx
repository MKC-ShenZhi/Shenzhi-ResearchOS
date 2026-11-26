"use client";

import type { MarkdownBlock as MarkdownBlockData } from "../../../../clients/backend/agent-message";
import type { CitationTarget } from "../citation-markers";
import { StreamdownRenderer } from "../streamdown-renderer";

export function MarkdownBlock({ block, citations, isStreaming = false }: {
  block: MarkdownBlockData; citations: readonly CitationTarget[]; isStreaming?: boolean;
}) {
  return <StreamdownRenderer content={block.content} citations={citations} isStreaming={isStreaming} />;
}
