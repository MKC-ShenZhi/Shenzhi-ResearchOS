"use client";

import { useEffect, useRef } from "react";
import { HtmlGenerator, parse } from "latex.js";
import "katex/dist/katex.min.css";
import { cn } from "@/lib/utils";
import { LATEX_LINK_PLACEHOLDER, replaceLatexLinks, splitLatexLinks } from "./latex-links";

type LatexRendererProps = {
  content: string;
  className?: string;
  "aria-label"?: string;
};

const LINK_CLASS_NAME =
  "[overflow-wrap:anywhere] text-primary underline decoration-primary/30 underline-offset-2 transition-colors hover:decoration-primary";

class LatexTextMacros {
  // Some sources use this symbol directly in prose.
  static symbols = new Map([["sigma", "σ"]]);
}

function createLink(text: string, href: string) {
  const link = document.createElement("a");
  link.href = href;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.className = LINK_CLASS_NAME;
  link.textContent = text;
  return link;
}

/** Restore URLs using their original source text. */
function restoreLinks(container: HTMLElement, links: ReturnType<typeof replaceLatexLinks>["links"]) {
  if (!links.length) return;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    if (LATEX_LINK_PLACEHOLDER.test(node.data)) textNodes.push(node);
  }
  for (const node of textNodes) {
    // The captured link indices occupy the odd positions in the split result.
    const parts = node.data.split(new RegExp(LATEX_LINK_PLACEHOLDER, "g"));
    node.replaceWith(...parts.map((part, index) => {
      if (index % 2 === 0) return part;
      const link = links[Number(part)];
      return link ? createLink(link.text, link.href) : "";
    }));
  }
}

export function LatexRenderer({ content, className, "aria-label": ariaLabel }: LatexRendererProps) {
  const renderedRef = useRef<HTMLDivElement>(null);
  const fallbackRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const container = renderedRef.current;
    const fallback = fallbackRef.current;
    if (!container || !fallback) return;

    try {
      const { source, links } = replaceLatexLinks(content);
      const generator = new HtmlGenerator({ hyphenate: false, CustomMacros: LatexTextMacros });
      parse(source, { generator });
      container.replaceChildren(generator.domFragment());
      restoreLinks(container, links);
      container.hidden = false;
      fallback.hidden = true;
    } catch (error) {
      // LaTeX.js uses its own SyntaxError class for malformed source.
      if (!(error instanceof Error && error.name === "SyntaxError")) {
        console.error("Failed to render content with LaTeX.js.", error);
      }
      container.replaceChildren();
      container.hidden = true;
      fallback.hidden = false;
    }

    return () => container.replaceChildren();
  }, [content]);

  return (
    <>
      <div
        ref={renderedRef}
        aria-label={ariaLabel}
        className={cn("latex-renderer max-w-full overflow-x-auto whitespace-pre-wrap", className)}
        hidden
      />
      <p ref={fallbackRef} className={cn("whitespace-pre-wrap", className)}>
        {splitLatexLinks(content).map((segment, index) => (
          segment.type === "link"
            ? <a key={index} href={segment.href} target="_blank" rel="noreferrer" className={LINK_CLASS_NAME}>{segment.text}</a>
            : segment.text
        ))}
      </p>
    </>
  );
}
