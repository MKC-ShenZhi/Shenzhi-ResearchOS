"use client";

import { useEffect, useRef } from "react";
import { HtmlGenerator, parse } from "latex.js";
import "katex/dist/katex.min.css";
import { cn } from "@/lib/utils";
import { LATEX_LINK_PLACEHOLDER, replaceLatexLinks, splitLatexLinks } from "./latex-links";

type LatexRendererProps = {
  content: string;
  className?: string;
  /** Render phrasing content without links, for use inside headings or links. */
  inline?: boolean;
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
function restoreLinks(container: DocumentFragment, links: ReturnType<typeof replaceLatexLinks>["links"]) {
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

function toInlineContent(fragment: DocumentFragment) {
  const body = fragment.firstElementChild;
  if (!body || fragment.childElementCount !== 1) return null;

  // LaTeX.js wraps the text in a body div and paragraphs. Wrapper elements
  // would interfere with heading line clamps and produce invalid inline markup.
  const paragraphs = Array.from(body.children);
  if (paragraphs.some((paragraph) => paragraph.tagName !== "P")) return null;

  const inline = document.createDocumentFragment();
  paragraphs.forEach((paragraph, index) => {
    if (index > 0) inline.append(" ");
    inline.append(...paragraph.childNodes);
  });
  for (const link of inline.querySelectorAll("a")) link.replaceWith(...link.childNodes);
  return inline;
}

export function LatexRenderer({ content, className, inline = false, "aria-label": ariaLabel }: LatexRendererProps) {
  const renderedRef = useRef<HTMLElement>(null);
  const fallbackRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const container = renderedRef.current;
    const fallback = fallbackRef.current;
    if (!container || !fallback) return;

    let rendered: DocumentFragment | null = null;
    try {
      if (!inline || /[\\$]/.test(content)) {
        const { source, links } = replaceLatexLinks(content);
        const generator = new HtmlGenerator({ hyphenate: false, CustomMacros: LatexTextMacros });
        parse(source, { generator });
        const fragment = generator.domFragment();
        restoreLinks(fragment, links);
        rendered = inline ? toInlineContent(fragment) : fragment;
      }
    } catch (error) {
      // LaTeX.js uses its own SyntaxError class for malformed source.
      if (!(error instanceof Error && error.name === "SyntaxError")) {
        console.error("Failed to render content with LaTeX.js.", error);
      }
    }
    if (rendered) container.replaceChildren(rendered);
    else container.replaceChildren();
    container.hidden = !rendered;
    fallback.hidden = Boolean(rendered);

    return () => container.replaceChildren();
  }, [content, inline]);

  const Rendered = inline ? "span" : "div";
  const Fallback = inline ? "span" : "p";

  return (
    <>
      <Rendered
        ref={(element) => { renderedRef.current = element; }}
        aria-label={ariaLabel}
        className={cn("latex-renderer", !inline && "max-w-full overflow-x-auto whitespace-pre-wrap", className)}
        hidden
      />
      <Fallback
        ref={(element) => { fallbackRef.current = element; }}
        className={cn(!inline && "whitespace-pre-wrap", className)}
      >
        {splitLatexLinks(content).map((segment, index) => (
          segment.type === "link" && !inline
            ? <a key={index} href={segment.href} target="_blank" rel="noreferrer" className={LINK_CLASS_NAME}>{segment.text}</a>
            : segment.text
        ))}
      </Fallback>
    </>
  );
}
