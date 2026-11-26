import type { ContentBlock } from "../../../clients/backend/agent-message";
import type { CitationTarget } from "./citation-markers";
import { MarkdownBlock } from "./blocks/markdown-block";

export function BlockRenderer({ block, citations, isStreaming = false }: {
  block: ContentBlock | { id: string; type: string };
  citations: readonly CitationTarget[]; isStreaming?: boolean;
}) {
  switch (block.type) {
    case "markdown":
      if ("content" in block && typeof block.content === "string") {
        return <MarkdownBlock block={{ id: block.id, type: "markdown", content: block.content }}
          citations={citations} isStreaming={isStreaming} />;
      }
      break;
  }
  return <p className="my-2 text-sm text-muted">暂不支持此内容的展示。</p>;
}
