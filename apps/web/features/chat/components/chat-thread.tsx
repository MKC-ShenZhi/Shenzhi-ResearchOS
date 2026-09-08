"use client";

import { useState } from "react";
import { Copy, RotateCcw, Sparkles } from "lucide-react";
import type { ChatTurn } from "../types";
import { referenceIdOf } from "../services/reference-navigation";
import { CitationScope } from "./citations";
import { ErrorBubble } from "./error-bubble";
import { MarkdownContent } from "./markdown-content";
import { ReasoningChainPanel } from "./reasoning-chain-panel";
import { ReferenceGrid } from "./reference-grid";
import { ThinkingStatusPanel } from "./thinking-status-panel";

function AssistantTurn({ turn, canResume, busy, onResume, onFollowup }: {
  turn: ChatTurn;
  canResume: boolean;
  busy: boolean;
  onResume: () => void;
  onFollowup: (question: string) => void;
}) {
  const [copyState, setCopyState] = useState("");
  // A persisted status is historical data. Only the current hook-owned
  // generation may make a turn render as actively streaming.
  const streaming = busy && turn.status === "streaming";
  const failed = turn.status === "failed";
  const stopped = turn.status === "stopped";
  const warnings = turn.warnings ?? [];
  const followups = turn.followups ?? [];
  const citationEnabled = !turn.knowledgeGrounding
    || turn.knowledgeGrounding === "grounded";

  return (
    <CitationScope referenceIds={citationEnabled
      ? turn.references.map((reference) => referenceIdOf(reference) ?? "")
      : []}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft">
          <Sparkles className="size-4 text-primary" />
        </span>
        <div className="min-w-0 max-w-[85%] flex-1 space-y-2">
          {(turn.thought || streaming || turn.readCount !== undefined || warnings.length > 0) && (
            <ThinkingStatusPanel
              thought={turn.thought}
              readCount={turn.readCount}
              durationMs={turn.durationMs}
              warnings={warnings}
              streaming={streaming}
              knowledgeGrounding={turn.knowledgeGrounding}
            />
          )}

          {turn.reasoning ? (
            <ReasoningChainPanel content={turn.reasoning} streaming={streaming} />
          ) : null}

          {failed && turn.error ? (
            <ErrorBubble
              message={turn.error}
              requestId={turn.requestId}
              onResume={onResume}
              canResume={canResume}
            />
          ) : (
            <div className="overflow-hidden rounded-2xl border border-line/60 bg-card shadow-card">
              <div className="flex items-center gap-2.5 border-b border-line/60 px-4 py-2.5">
                <span className="text-sm font-semibold text-ink">深知 AI</span>
                {turn.durationMs !== undefined && turn.durationMs > 0 && (
                  <span className="text-xs text-faint">· 耗时 {(turn.durationMs / 1000).toFixed(1)}s</span>
                )}
              </div>
              <div className="px-4 py-3 text-[15px] leading-relaxed text-ink-2">
                {turn.content ? (
                  <MarkdownContent text={turn.content} />
                ) : streaming ? (
                  <p className="animate-pulse text-sm text-muted">正在思考…</p>
                ) : (
                  "\u00A0"
                )}
                {streaming && turn.content && (
                  <span className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-primary align-[-2px]" />
                )}
              </div>
            </div>
          )}

          {!failed && turn.error && (
            <ErrorBubble
              message={turn.error}
              requestId={turn.requestId}
              onResume={onResume}
              canResume={canResume}
            />
          )}

          {stopped && (
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <span>已停止生成（内容仅为部分回复）</span>
              {canResume && (
                <button type="button" disabled={busy} onClick={onResume} className="text-primary hover:underline disabled:opacity-50">
                  继续生成
                </button>
              )}
            </div>
          )}

          <ReferenceGrid
            references={turn.references ?? []}
            answer={turn.content}
            knowledgeGrounding={turn.knowledgeGrounding}
          />

          <div className="flex gap-3 text-xs text-muted">
            {turn.content && (
              <button
                type="button"
                className="inline-flex cursor-pointer items-center gap-1 hover:text-primary"
                onClick={() => {
                  void navigator.clipboard.writeText(turn.content).then(
                    () => setCopyState("已复制"),
                    () => setCopyState("复制失败"),
                  );
                }}
              >
                <Copy className="size-3" />
                {copyState || "复制"}
              </button>
            )}
            {canResume && !failed && (
              <button
                type="button"
                disabled={busy}
                onClick={onResume}
                className="inline-flex cursor-pointer items-center gap-1 text-primary disabled:opacity-50"
              >
                <RotateCcw className="size-3" />
                {turn.messageId ? "继续生成" : "重试"}
              </button>
            )}
          </div>

          {followups.length > 0 && (
            <div className="flex flex-col gap-2">
              {followups.map((question) => (
                <button
                  key={question}
                  type="button"
                  disabled={busy}
                  onClick={() => onFollowup(question)}
                  className="cursor-pointer rounded-xl border border-line bg-card px-3.5 py-2.5 text-left text-[13px] text-muted transition-colors hover:border-primary/40 hover:text-primary disabled:opacity-50"
                >
                  {question}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </CitationScope>
  );
}

/** Agent B 风格对话流：头像 + 思考状态 + 推理链 + 品牌回答卡片 */
export function ChatThread({ turns, busy, onResume, onFollowup }: {
  turns: ChatTurn[];
  busy: boolean;
  onResume: () => void;
  onFollowup: (question: string) => void;
}) {
  return (
    <div className="space-y-6">
      {turns.map((turn, index) =>
        turn.role === "user" ? (
          <div key={turn.localId} className="flex justify-end">
            <p className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-white">
              {turn.content}
            </p>
          </div>
        ) : (
          <AssistantTurn
            key={turn.localId}
            turn={turn}
            busy={busy}
            onResume={onResume}
            onFollowup={onFollowup}
            canResume={index === turns.length - 1 && ["done", "failed", "stopped"].includes(turn.status)}
          />
        ),
      )}
    </div>
  );
}
