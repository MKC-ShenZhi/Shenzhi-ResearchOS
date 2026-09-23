"use client";

import { useEffect, useRef, useState } from "react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { ErrorBubble } from "@/features/chat/components/error-bubble";
import { MarkdownContent } from "@/features/chat/components/markdown-content";
import { usePaperAgent } from "../use-paper-agent";

const PAPER_PROMPTS = [
  "这篇论文主要解决什么问题？",
  "论文的核心贡献是什么？",
  "作者采用了什么方法？",
  "这篇论文的主要结论是什么？",
];

export function PaperAssistantPanel({ paper }: { paper: KnowledgePaperDetail }) {
  const [value, setValue] = useState("");
  const { turns, running, activity, send, stop } = usePaperAgent(paper);
  const threadRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const disabled = running;

  useEffect(() => {
    const node = threadRef.current;
    if (node && nearBottom.current) node.scrollTop = node.scrollHeight;
  }, [turns]);

  const submit = (question: string) => {
    if (disabled || !question.trim()) return;
    setValue("");
    nearBottom.current = true;
    void send(question);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line p-4 text-xs leading-relaxed text-muted">
        <p>Assistant 可读取当前论文 PDF 并根据正文回答问题；扫描件、图表和图片中的内容可能无法识别。</p>
      </div>
      <div ref={threadRef} onScroll={(event) => {
        const node = event.currentTarget;
        nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
      }} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4" aria-label="论文问答消息" aria-busy={running}>
        {turns.length === 0 && (
          <div className="grid grid-cols-2 gap-2">
            {PAPER_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                disabled={disabled}
                onClick={() => submit(prompt)}
                className="min-h-20 rounded-xl border border-line bg-card p-3 text-left text-sm leading-5 text-primary transition-colors hover:bg-primary-soft disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
        {turns.map((turn) => (
          <div
            key={turn.localId}
            className={turn.role === "user"
              ? "ml-auto max-w-[88%] break-words rounded-xl bg-primary-soft p-3 text-sm text-ink-2"
              : "break-words text-sm leading-7 text-ink-2"}
          >
            <p className="mb-2 text-xs font-semibold text-muted">{turn.role === "user" ? "你" : "Assistant"}</p>
            {turn.role === "user" ? <p className="whitespace-pre-wrap">{turn.content}</p> : <>
              {turn.content && <MarkdownContent text={turn.content} />}
              {running && turn.status === "streaming" && !turn.content && (
                <p role="status" className="animate-pulse">
                  {activity === "reading_pdf" ? "正在阅读论文 PDF…" : "正在分析问题…"}
                </p>
              )}
              {turn.warnings.map((warning) => <p key={warning} className="mt-2 text-xs text-muted">{warning}</p>)}
              {turn.error && <ErrorBubble message={turn.error} requestId={turn.requestId} canResume={false} onResume={() => {}} />}
              {turn.status === "stopped" && <p className="mt-2 text-xs text-muted">已停止生成</p>}
            </>}
          </div>
        ))}
      </div>
      <form className="shrink-0 space-y-2 border-t border-line p-4" onSubmit={(event) => { event.preventDefault(); submit(value); }}>
        <textarea aria-label="向论文 Assistant 提问" placeholder="询问这篇论文的正文内容…" maxLength={2000} rows={3} value={value} disabled={disabled} onChange={(event) => setValue(event.target.value)} className="w-full resize-none rounded-xl border border-line bg-panel p-3 text-sm outline-none focus:border-primary disabled:opacity-50" />
        {running ? <button type="button" onClick={stop} className="text-sm text-primary">停止生成</button> : <button type="submit" disabled={disabled || !value.trim()} className="rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50">发送</button>}
      </form>
    </div>
  );
}
