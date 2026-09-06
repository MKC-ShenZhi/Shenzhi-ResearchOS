"use client";

import { useEffect, useRef, useState } from "react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { useAuth } from "@/components/auth/auth-provider";
import { useChatSession } from "@/features/chat/hooks/use-chat-session";
import { chatIdentityScope, type ChatIdentityScope } from "@/features/chat/services/identity-scope";
import { MarkdownContent } from "@/features/chat/components/markdown-content";
import { ErrorBubble } from "@/features/chat/components/error-bubble";

export function PaperAssistantPanel({ paper }: { paper: KnowledgePaperDetail }) {
  const { session, isPending } = useAuth();
  const identityScope = chatIdentityScope(session?.user.id);
  const [bootstrapped, setBootstrapped] = useState(() => !isPending);
  useEffect(() => {
    if (!isPending) queueMicrotask(() => setBootstrapped(true));
  }, [isPending]);
  if (!bootstrapped) return <p className="p-4 text-sm text-muted">正在加载会话…</p>;
  return <PaperAssistant key={`${identityScope}:${paper.id}`} paper={paper} identityScope={identityScope} />;
}

function PaperAssistant({ paper, identityScope }: { paper: KnowledgePaperDetail; identityScope: ChatIdentityScope }) {
  const [value, setValue] = useState("");
  const { turns, busy, interactionLocked, send, stop, resumeLast } = useChatSession({ identityScope, embedded: true });
  const threadRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const insufficient = !paper.abstract?.trim();
  const disabled = busy || interactionLocked || insufficient;

  useEffect(() => {
    const node = threadRef.current;
    if (node && nearBottom.current) node.scrollTop = node.scrollHeight;
  }, [turns]);

  const submit = (question: string) => {
    if (disabled || !question.trim()) return;
    setValue("");
    nearBottom.current = true;
    void send({
      question, mode: "fast", model: "default", web_search: false,
      capabilities: { knowledge: { enabled: false } },
      attachments: [{ kind: "paper", ref_id: paper.id, title: paper.title.slice(0, 500) }],
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line p-4 text-xs leading-relaxed text-muted">
        <p>仅基于当前论文的元信息与摘要回答，尚未读取 PDF 全文。</p>
        {insufficient && <p role="status" className="mt-2 text-amber-700">当前论文缺少摘要，可用于 AI 理解的信息不足，暂无法提问。</p>}
      </div>
      <div ref={threadRef} onScroll={(event) => {
        const node = event.currentTarget;
        nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
      }} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4" aria-label="论文问答消息" aria-busy={busy}>
        {turns.length === 0 && <button disabled={disabled} onClick={() => submit("这篇论文主要解决什么问题？")} className="rounded-xl border border-line p-3 text-left text-sm text-primary disabled:opacity-50">这篇论文主要解决什么问题？</button>}
        {turns.map((turn, index) => (
          <div key={turn.localId} className="break-words rounded-xl bg-panel p-3 text-sm text-ink-2">
            <p className="mb-2 text-xs font-semibold text-muted">{turn.role === "user" ? "你" : "Assistant"}</p>
            {turn.role === "user" ? <p className="whitespace-pre-wrap">{turn.content}</p> : <>
              {turn.content && <MarkdownContent text={turn.content} />}
              {busy && turn.status === "streaming" && !turn.content && <p className="animate-pulse">正在读取论文资料并生成回答…</p>}
              {turn.warnings.map((warning) => <p key={warning} className="mt-2 text-xs text-muted">{warning}</p>)}
              {turn.error && <ErrorBubble message={turn.error} canResume={!disabled && index === turns.length - 1} onResume={() => void resumeLast()} />}
              {turn.status === "stopped" && <p className="mt-2 text-xs text-muted">已停止生成{index === turns.length - 1 && <button disabled={disabled} onClick={() => void resumeLast()} className="ml-2 text-primary">继续生成</button>}</p>}
            </>}
          </div>
        ))}
      </div>
      <form className="shrink-0 space-y-2 border-t border-line p-4" onSubmit={(event) => { event.preventDefault(); submit(value); }}>
        <textarea aria-label="向论文 Assistant 提问" placeholder="根据摘要，询问这篇论文…" maxLength={2000} rows={3} value={value} disabled={disabled} onChange={(event) => setValue(event.target.value)} className="w-full resize-none rounded-xl border border-line bg-panel p-3 text-sm outline-none focus:border-primary disabled:opacity-50" />
        {busy ? <button type="button" onClick={() => void stop()} className="text-sm text-primary">停止生成</button> : <button type="submit" disabled={disabled || !value.trim()} className="rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50">发送</button>}
      </form>
    </div>
  );
}
