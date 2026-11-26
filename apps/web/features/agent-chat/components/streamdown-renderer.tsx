"use client";

import { memo, useMemo } from "react";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { defaultRehypePlugins, Streamdown, type StreamdownProps } from "streamdown";
import "katex/dist/katex.min.css";
import { cn } from "../../../lib/utils";
import { markdownElements } from "../../../components/renderers/markdown-elements";
import { normalizeMathDelimiters } from "../../../components/renderers/math-delimiters";
import { remarkCitations, type CitationTarget } from "./citation-markers";

type StreamdownRendererProps = {
  content: string;
  className?: string;
  isStreaming?: boolean;
  citations?: readonly CitationTarget[];
};

const remarkPlugins: StreamdownProps["remarkPlugins"] = [remarkGfm, remarkMath];
// Sanitize model output before KaTeX generates its HTML and MathML.
const rehypePlugins: StreamdownProps["rehypePlugins"] = [
  defaultRehypePlugins.sanitize,
  defaultRehypePlugins.undoubleClobberPrefix,
  defaultRehypePlugins.harden,
  [rehypeKatex, { trust: false, strict: "ignore" }],
];
const EMPTY_CITATIONS: readonly CitationTarget[] = [];

export const StreamdownRenderer = memo(function StreamdownRenderer({
  content,
  className,
  isStreaming = false,
  citations = EMPTY_CITATIONS,
}: StreamdownRendererProps) {
  const plugins = useMemo<StreamdownProps["remarkPlugins"]>(() => [
    ...remarkPlugins!, [remarkCitations, { citations, isStreaming }],
  ], [citations, isStreaming]);
  const components = useMemo<StreamdownProps["components"]>(() => ({
    ...markdownElements,
    inlineCode: markdownElements.code,
    a: ({ href, children }) => {
      // rehype-sanitize prefixes fragment links to prevent DOM clobbering.
      // Resolve only our generated targets and retain sanitization for all others.
      const citation = citations.find((target) => target.href === href
        || `#user-content-${target.href.slice(1)}` === href);
      return citation ? (
        <sup className="ml-0.5 inline-flex align-super text-[10px] leading-none">
          <a href={citation.href} aria-label={`查看参考来源 ${citation.number}：${citation.title}`}
            title={citation.title}
            className="inline-flex min-h-5 min-w-5 items-center justify-center rounded-full bg-chip px-1.5 font-medium text-ink-2 no-underline transition-colors hover:bg-primary-soft hover:text-primary focus-visible:outline-2 focus-visible:outline-primary">
            {citation.number}
          </a>
        </sup>
      ) : markdownElements.a({ href, children });
    },
  }), [citations]);
  return (
    <Streamdown
      className={cn("min-w-0 space-y-0 break-words text-[15px] leading-7", className)}
      mode={isStreaming ? "streaming" : "static"}
      isAnimating={isStreaming}
      components={components}
      controls={false}
      skipHtml
      remarkPlugins={plugins}
      rehypePlugins={rehypePlugins}
    >
      {normalizeMathDelimiters(content)}
    </Streamdown>
  );
});
