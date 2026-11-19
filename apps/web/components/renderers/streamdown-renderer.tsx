"use client";

import { memo } from "react";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { defaultRehypePlugins, Streamdown, type StreamdownProps } from "streamdown";
import "katex/dist/katex.min.css";
import { cn } from "@/lib/utils";
import { markdownElements } from "./markdown-elements";
import { normalizeMathDelimiters } from "./math-delimiters";

type StreamdownRendererProps = {
  content: string;
  className?: string;
  isStreaming?: boolean;
};

const remarkPlugins: StreamdownProps["remarkPlugins"] = [remarkGfm, remarkMath];
// Sanitize model output before KaTeX generates its HTML and MathML.
const rehypePlugins: StreamdownProps["rehypePlugins"] = [
  defaultRehypePlugins.sanitize,
  defaultRehypePlugins.undoubleClobberPrefix,
  defaultRehypePlugins.harden,
  [rehypeKatex, { trust: false, strict: "ignore" }],
];
const components = { ...markdownElements, inlineCode: markdownElements.code };

export const StreamdownRenderer = memo(function StreamdownRenderer({
  content,
  className,
  isStreaming = false,
}: StreamdownRendererProps) {
  return (
    <Streamdown
      className={cn("min-w-0 space-y-0 break-words text-[15px] leading-7", className)}
      mode={isStreaming ? "streaming" : "static"}
      isAnimating={isStreaming}
      components={components}
      controls={false}
      skipHtml
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
    >
      {normalizeMathDelimiters(content)}
    </Streamdown>
  );
});
