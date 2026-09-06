"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, Sparkles } from "lucide-react";
import { ComposerShell } from "./composer";
import { ChatThread } from "./chat-thread";
import { useChatSession } from "../hooks/use-chat-session";
import { chatInputFromComposer, capabilitiesForEntryMode } from "../services/conversation";
import { readAskDraft } from "../services/draft";
import { chatIdentityScope, type ChatIdentityScope } from "../services/identity-scope";
import { getChatConfig } from "@/clients/backend/chat";
import { askSessionUrl, normalizeAskSessionId } from "../services/session-url";
import type { ChatAttachment, ChatModelId, ChatReplyMode, ComposerSubmitPayload, ChatConfig } from "@/types/ai-search";
import type { ComposerEntryMode } from "@/types";
import { DEFAULT_CHAT_MODEL } from "@/lib/data/chat-models";
import { useAuth } from "@/components/auth/auth-provider";
import { AnonymousClaimCoordinator } from "./anonymous-claim-coordinator";

const SUGGESTIONS = [
  "帮我总结一下扩散模型在机器人控制中的最新进展",
  "RDT-1B 和 π0 的技术路线有什么差异?",
  "推荐几篇机器人基础模型方向值得精读的论文",
  "帮我起草一份关于操作泛化性的研究计划",
];

interface AgentChatProps {
  question?: string;
  initialMode?: ChatReplyMode;
  initialModel?: ChatModelId;
  initialWebSearch?: boolean;
  initialSessionId?: string | null;
  invalidSession?: boolean;
}

export function AgentChat(props: AgentChatProps) {
  const { session, isPending } = useAuth();
  const identityScope = chatIdentityScope(session?.user.id);
  const [initialQuestionConsumed, setInitialQuestionConsumed] = useState(false);
  const [authBootstrapComplete, setAuthBootstrapComplete] = useState(() => !isPending);

  useEffect(() => {
    if (isPending) return;
    let live = true;
    queueMicrotask(() => {
      if (live) setAuthBootstrapComplete(true);
    });
    return () => { live = false; };
  }, [isPending]);

  // Only this mounted AgentChat's first auth bootstrap owns the loading screen.
  // A later Better Auth focus refresh must not tear down its ChatWorkspace.
  if (isPending && !authBootstrapComplete) {
    return <p className="p-6 text-sm text-muted">正在加载会话…</p>;
  }

  return (
    <>
      <AnonymousClaimCoordinator />
      <ChatWorkspace
        key={identityScope}
        {...props}
        identityScope={identityScope}
        question={initialQuestionConsumed ? "" : props.question}
        onInitialQuestion={() => setInitialQuestionConsumed(true)}
      />
    </>
  );
}

/** 对话历史统一在 AppSidebar；此处仅保留主对话区 */
function ChatWorkspace({
  question = "",
  initialMode,
  initialModel,
  initialWebSearch,
  initialSessionId,
  invalidSession,
  onInitialQuestion,
  identityScope,
}: AgentChatProps & { identityScope: ChatIdentityScope; onInitialQuestion: () => void }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const desiredSessionId = normalizeAskSessionId(searchParams.get("session") ?? undefined);
  const [value, setValue] = useState("");
  const [mode, setMode] = useState<ChatReplyMode>(initialMode ?? "fast");
  const [model, setModel] = useState(initialModel ?? DEFAULT_CHAT_MODEL);
  const [webSearch, setWebSearch] = useState(Boolean(initialWebSearch));
  const [entryMode, setEntryMode] = useState<ComposerEntryMode>("ai");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [config, setConfig] = useState<ChatConfig>();
  const [showJump, setShowJump] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const initialQuestionStarted = useRef(false);
  const routeSessionId = useRef(initialSessionId);
  const syncSessionUrl = useCallback((id: string | null) => {
    if (typeof window === "undefined") return;
    const nextUrl = askSessionUrl(id);
    const currentUrl = `${window.location.pathname}${window.location.search}`;
    if (currentUrl === nextUrl) return;
    // The first turn commonly starts on /agents. Keep that live Chat
    // component mounted while exposing the canonical ask URL; a route
    // navigation here would run its cleanup and cancel the new SSE stream.
    window.history.replaceState(window.history.state, "", nextUrl);
  }, []);
  const {
    turns,
    busy,
    hydrating,
    interactionLocked,
    sessionPreferences,
    phase,
    loadError,
    resolvedInitialSessionId,
    send,
    stop,
    resumeLast,
    reset,
    openSession,
  } = useChatSession({
    identityScope,
    initialSessionId,
    desiredSessionId,
    onSessionIdChange: syncSessionUrl,
  });

  useEffect(() => {
    if (!invalidSession) return;
    reset();
  }, [invalidSession, reset]);

  useEffect(() => {
    let live = true;
    void getChatConfig().then((loaded) => {
      if (live) setConfig(loaded);
    });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (routeSessionId.current !== resolvedInitialSessionId) {
      // A route transition owns the question now; a late config response from
      // the previous route must never auto-send it into the restored session.
      initialQuestionStarted.current = true;
      routeSessionId.current = resolvedInitialSessionId;
    }
  }, [resolvedInitialSessionId]);

  useEffect(() => {
    if (!config || resolvedInitialSessionId || !question.trim() || initialQuestionStarted.current) return;
    initialQuestionStarted.current = true;
    const draft = readAskDraft(question);
    const preferred = initialModel ?? draft.model;
    const selected = config.models.some((m) => m.value === preferred && m.enabled)
      ? preferred
      : config.default_model ?? config.models.find((m) => m.enabled)?.value ?? preferred;
    setModel(selected);
    const selectedMode = initialMode ?? draft.mode;
    const web = initialWebSearch ?? draft.web_search;
    setMode(selectedMode);
    setWebSearch(web);
    const capabilities = capabilitiesForEntryMode("ai");
    onInitialQuestion();
    void send({
      question,
      mode: selectedMode,
      model: selected,
      web_search: web,
      attachments: draft.attachments,
      capabilities,
    });
  }, [config, initialMode, initialModel, initialWebSearch, onInitialQuestion, question, resolvedInitialSessionId, send]);

  useEffect(() => {
    if (nearBottom.current) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  useEffect(() => {
    if (!sessionPreferences) return;
    let live = true;
    queueMicrotask(() => {
      if (!live) return;
      setMode(sessionPreferences.mode);
      setModel(sessionPreferences.model);
      setWebSearch(sessionPreferences.webSearch);
      setEntryMode(sessionPreferences.entryMode);
    });
    return () => { live = false; };
  }, [sessionPreferences]);

  const submit = (payload: ComposerSubmitPayload) => {
    if (busy || interactionLocked) return;
    if (!payload.question.trim()) return;
    initialQuestionStarted.current = true;
    nearBottom.current = true;
    setValue("");
    setAttachments([]);
    if (payload.entryMode === "search") {
      router.push(`/knowledge/search?q=${encodeURIComponent(payload.question)}`);
      return;
    }
    const request = chatInputFromComposer(payload);
    setEntryMode(payload.entryMode);
    void send(request);
  };

  const followup = (text: string) => {
    submit({ entryMode, question: text, mode, model, web_search: webSearch, attachments: [] });
  };

  const composer = (
    <ComposerShell
      value={value}
      onChange={setValue}
      onSend={submit}
      placeholder="输入研究问题…"
      replyMode={mode}
      onReplyModeChange={setMode}
      model={model}
      onModelChange={setModel}
      webSearch={webSearch}
      onWebSearchChange={setWebSearch}
      attachments={attachments}
      onAttachmentsChange={setAttachments}
      entryMode={entryMode}
      onEntryModeChange={setEntryMode}
      config={config}
      busy={busy}
      disabled={interactionLocked}
      onStop={() => void stop()}
    />
  );

  return (
    <div className="flex h-screen min-w-0 flex-1 flex-col">
      {turns.length === 0 ? (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 overflow-auto px-6">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-primary-soft">
            <Sparkles className="size-6 text-primary" />
          </span>
          <h1 className="text-xl font-semibold text-ink">
            {hydrating
              ? "正在加载对话…"
              : phase === "STALE"
                ? "该对话已过期或不存在。"
                : loadError
                  ? "对话加载失败"
                  : "有什么我可以帮你研究的?"}
          </h1>
          {phase === "STALE" && (
            <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-muted">
              <span>请新建对话继续。</span>
              <button
                type="button"
                onClick={() => reset()}
                className="rounded-lg bg-primary px-3 py-1.5 text-white hover:bg-primary-deep"
              >
                新建对话
              </button>
            </div>
          )}
          {loadError && phase !== "STALE" && (
            <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-muted">
              <span>{loadError}</span>
              {resolvedInitialSessionId && (
                <button
                  type="button"
                  onClick={() => void openSession(resolvedInitialSessionId)}
                  className="rounded-lg border border-line bg-card px-3 py-1.5 text-ink-2 hover:bg-chip"
                >
                  重试
                </button>
              )}
            </div>
          )}
          <div className="w-full max-w-5xl">{composer}</div>
          <div className="flex max-w-5xl flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((text) => (
              <button
                key={text}
                type="button"
                disabled={busy || interactionLocked}
                onClick={() => followup(text)}
                className="cursor-pointer rounded-full border border-line bg-card px-3.5 py-1.5 text-[13px] text-muted transition-colors hover:border-primary/40 hover:text-primary"
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          <header className="flex h-12 shrink-0 items-center border-b border-line px-6">
            <h1 className="truncate text-sm font-medium text-ink">{turns[0]?.content}</h1>
          </header>
          <div
            className="scrollbar-subtle min-h-0 flex-1 overflow-y-auto"
            onScroll={(event) => {
              const element = event.currentTarget;
              nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100;
              setShowJump(!nearBottom.current);
            }}
          >
            <div className="mx-auto max-w-5xl space-y-5 px-6 py-8">
              <ChatThread turns={turns} busy={busy} onResume={() => void resumeLast()} onFollowup={followup} />
              <Link href={`/knowledge/search?q=${encodeURIComponent(turns[0]?.content ?? "")}`} className="inline-block text-xs text-primary">
                相关论文
              </Link>
              <div ref={bottomRef} />
            </div>
          </div>
          <div className="relative px-6 pb-5 pt-2">
            {showJump && (
              <button
                type="button"
                aria-label="跳到最新"
                onClick={() => {
                  nearBottom.current = true;
                  bottomRef.current?.scrollIntoView({ behavior: "smooth" });
                }}
                className="absolute -top-12 left-1/2 flex size-9 -translate-x-1/2 items-center justify-center rounded-full border border-line bg-card text-muted shadow-pop"
              >
                <ChevronDown className="size-4" />
              </button>
            )}
            <div className="mx-auto max-w-5xl">{composer}</div>
          </div>
        </>
      )}
    </div>
  );
}
