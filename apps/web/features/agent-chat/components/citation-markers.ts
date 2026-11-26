/** Markdown AST extension: citations are links, never rewritten inside code/math. */
export interface CitationTarget {
  id: string;
  number: number;
  href: string;
  title: string;
}

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
}

const SKIP = new Set(["code", "inlineCode", "math", "inlineMath", "html", "link", "linkReference", "image", "imageReference", "definition"]);

export function remarkCitations({ citations, isStreaming }: {
  citations: readonly CitationTarget[]; isStreaming: boolean;
}) {
  const targets = new Map(citations.map((citation) => [citation.id, citation]));
  function textNodes(value: string): MarkdownNode[] {
    // A partial marker is withheld until it is complete; source IDs never flash.
    const start = value.lastIndexOf("[[");
    if (start >= 0 && !value.slice(start).includes("]]")) {
      const suffix = value.slice(start);
      if ("[[cite:".startsWith(suffix) || suffix.startsWith("[[cite:")) {
        value = value.slice(0, start) + (isStreaming ? "" : "[引用不可用]");
      }
    }
    const nodes: MarkdownNode[] = [];
    let cursor = 0;
    for (const match of value.matchAll(/\[\[cite:([^\[\]\r\n]*)\]\]/g)) {
      if (match.index > cursor) nodes.push({ type: "text", value: value.slice(cursor, match.index) });
      const citation = targets.get(match[1]);
      nodes.push(citation
        ? { type: "link", url: citation.href, children: [{ type: "text", value: String(citation.number) }] }
        : { type: "text", value: "[引用不可用]" });
      cursor = match.index + match[0].length;
    }
    if (cursor < value.length) nodes.push({ type: "text", value: value.slice(cursor) });
    return nodes;
  }
  function visit(node: MarkdownNode): void {
    if (SKIP.has(node.type) || !node.children) return;
    // Streamdown's incomplete-link repair can turn [[cite:... into a text "["
    // followed by a synthetic link. Restore that fragment before citation parsing;
    // real Markdown links, code and math keep their original semantics.
    const children: MarkdownNode[] = [];
    for (const child of node.children) {
      const previous = children.at(-1);
      const label = child.children?.map((part) => part.value ?? "").join("") ?? "";
      if (child.type === "link" && child.url === "streamdown:incomplete-link"
        && previous?.type === "text" && previous.value?.endsWith("[")
        && ("cite:".startsWith(label) || label.startsWith("cite:"))) {
        previous.value += `[${label}`;
      } else children.push(child);
    }
    node.children = children.flatMap((child) => {
      if (child.type === "text") return textNodes(child.value ?? "");
      visit(child);
      return [child];
    });
  }
  return visit;
}
