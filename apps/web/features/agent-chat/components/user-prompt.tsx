"use client";

import { useId, type ReactNode } from "react";
import { Quote } from "lucide-react";
import { MarkdownRenderer } from "@/components/renderers/markdown-renderer";
import { quotedPromptParts } from "../quoted-prompt";

/** Quote context is an attachment-like disclosure, separate from the user's words. */
export function UserPrompt({ content, children, appearance = "message" }: {
  content: string;
  children?: ReactNode;
  appearance?: "message" | "steer";
}) {
  const { question, quote } = quotedPromptParts(content);
  const quoteId = useId();
  return <div className="flex min-w-0 max-w-[90%] flex-col items-end gap-2 sm:max-w-[75%]">
    {quote && <div className="group/quote relative min-w-0 max-w-full" data-user-quote>
      <button type="button" aria-describedby={quoteId}
        className="peer flex w-fit max-w-full cursor-default items-center gap-1.5 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted transition-colors hover:bg-chip focus-visible:outline-2 focus-visible:outline-primary">
        <Quote className="size-3.5 shrink-0" aria-hidden />
        <span>1 个已选文本片段</span>
      </button>
      <div id={quoteId} role="tooltip"
        className="invisible absolute bottom-full right-0 z-30 w-[360px] max-w-[calc(100vw-32px)] pb-2 group-hover/quote:visible peer-focus-visible:visible">
        <blockquote className="max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-xl border border-line bg-card px-3 py-2 text-left text-[13px] leading-6 text-muted shadow-lg">{quote}</blockquote>
      </div>
    </div>}
    <div data-user-question className={appearance === "steer"
      ? "min-w-0 max-w-full break-words rounded-2xl rounded-br-md border border-agent/30 bg-agent-soft px-3.5 py-2 text-[14px] leading-6 text-ink"
      : "min-w-0 max-w-full break-words rounded-3xl bg-chip px-4 py-2.5 text-[15px] leading-7 text-ink"}>
      <MarkdownRenderer content={question}
        className="[&>:first-child]:mt-0 [&>:last-child]:mb-0 [&_p]:whitespace-pre-wrap" />
      {children}
    </div>
  </div>;
}
