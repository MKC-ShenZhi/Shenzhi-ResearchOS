import type { ContentBlock, Reference } from "../../../clients/backend/agent-message";
import { MarkdownBlock } from "./blocks/markdown-block";

export function BlockRenderer({ block, references, anchorPrefix, isStreaming = false }: {
  block: ContentBlock | { id: string; type: string };
  references: readonly Reference[]; anchorPrefix: string; isStreaming?: boolean;
}) {
  switch (block.type) {
    case "markdown":
      if ("content" in block && typeof block.content === "string") {
        return <MarkdownBlock block={{ id: block.id, type: "markdown", content: block.content }}
          references={references} anchorPrefix={anchorPrefix} isStreaming={isStreaming} />;
      }
      break;
  }
  return <p className="my-2 text-sm text-muted">暂不支持此内容的展示。</p>;
}
