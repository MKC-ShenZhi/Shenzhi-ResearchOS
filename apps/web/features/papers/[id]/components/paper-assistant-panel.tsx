"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Flag, FlaskConical, Info, Lightbulb, Sparkles, Square, Target } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { ErrorBubble } from "@/features/chat/components/error-bubble";
import { MarkdownContent } from "@/features/chat/components/markdown-content";
import { usePaperAgent } from "../use-paper-agent";

const PAPER_PROMPTS = [
  { icon: Target, text: "这篇论文主要解决什么问题？" },
  { icon: Lightbulb, text: "论文的核心贡献是什么？" },
  { icon: FlaskConical, text: "作者采用了什么方法？" },
  { icon: Flag, text: "这篇论文的主要结论是什么？" },
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
      <div ref={threadRef} onScroll={(event) => {
        const node = event.currentTarget;
        nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
      }} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4" aria-label="论文问答消息" aria-busy={running}>
        {turns.length === 0 && (
          <div className="flex min-h-full flex-col justify-center py-4">
            <div className="mb-5 flex flex-col items-center text-center">
              <span className="flex size-11 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                <Sparkles className="size-5" />
              </span>
              <p className="mt-3 text-base font-semibold text-ink">向这篇论文提问</p>
              <p className="mt-1 text-xs text-muted">基于论文正文回答，点击下方问题快速开始</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {PAPER_PROMPTS.map(({ icon: Icon, text }) => (
                <button
                  key={text}
                  type="button"
                  disabled={disabled}
                  onClick={() => submit(text)}
                  className="flex min-h-[4.5rem] flex-col items-start gap-2 rounded-xl border border-line bg-card p-3 text-left text-[13px] leading-5 text-ink-2 transition-colors hover:border-primary/40 hover:bg-primary-soft hover:text-primary disabled:opacity-50"
                >
                  <Icon className="size-4 text-primary" />
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn) => (
          <div
            key={turn.localId}
            className={turn.role === "user"
              ? "ml-auto max-w-[88%] break-words rounded-xl bg-primary-soft p-3 text-sm text-ink-2"
              : "break-words text-sm leading-7 text-ink-2"}
          >
            {turn.role === "user"
              ? <p className="mb-1 text-xs font-semibold text-muted">你</p>
              : <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted"><Sparkles className="size-3.5 text-primary" />Assistant</p>}
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
      <form className="shrink-0 px-4 pb-3 pt-2" onSubmit={(event) => { event.preventDefault(); submit(value); }}>
        <div className="rounded-2xl border border-line bg-card shadow-card transition-colors focus-within:border-primary/60">
          <textarea aria-label="向论文 Assistant 提问" placeholder="询问这篇论文的正文内容…" maxLength={2000} rows={3} value={value} disabled={disabled} onChange={(event) => setValue(event.target.value)} className="block w-full resize-none bg-transparent px-3.5 pt-3 text-base outline-none placeholder:text-faint disabled:opacity-50 sm:text-sm" />
          <div className="flex justify-end px-2 pb-2">
            {running ? (
              <button type="button" onClick={stop} aria-label="停止生成" title="停止生成" className="flex size-8 items-center justify-center rounded-full bg-ink text-card transition-colors hover:bg-ink/90">
                <Square className="size-3 fill-current" />
              </button>
            ) : (
              <button type="submit" aria-label="发送" title="发送" disabled={disabled || !value.trim()} className="flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground transition-colors hover:bg-primary-deep disabled:cursor-not-allowed disabled:bg-chip disabled:text-faint">
                <ArrowUp className="size-4" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>
        <p className="mt-2 flex items-start gap-1 text-[11px] leading-4 text-faint">
          <Info className="mt-px size-3 shrink-0" />
          Assistant 可读取当前论文 PDF 并根据正文回答问题；扫描件、图表和图片中的内容可能无法识别。
        </p>
      </form>
    </div>
  );
}
