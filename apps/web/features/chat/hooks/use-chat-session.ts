"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { getChatSession, resumeChatMessage, stopChatMessage, streamChatMessage } from "@/clients/backend/chat";
import { useAskSidebarBridge } from "@/stores/ask-sidebar-bridge";
import { beginTurn, restoreTurns } from "../services/conversation";
import { clearAskDraft } from "../services/draft";
import { isAbortError, isMissingSessionError, messageForApiError } from "../services/errors";
import { readCurrentSessionId } from "../services/session-url";
import {
  deleteLocalAskSession,
  getLocalAskSession,
  titleFromQuestion,
  upsertLocalAskSession,
  type LocalAskSession,
} from "../services/local-history";
import {
  phaseForRestoredStatus,
  SessionGenerationGate,
  type ChatSessionPhase,
  type SessionGenerationHandle,
} from "../services/session-hydration";
import { transitionSessionNavigation } from "../services/session-navigation";
import type { ChatIdentityScope } from "../services/identity-scope";
import type { ChatSendInput, ChatSessionPreferences, ChatTurn } from "../types";
import type { ChatMessageStatus, ChatModelId, ChatReplyMode } from "@/types/ai-search";

const newTurn = (role: ChatTurn["role"], content = ""): ChatTurn => ({
  localId: crypto.randomUUID(), role, content, reasoning: "", thought: "正在连接生成服务…",
  status: role === "user" ? "done" : "streaming", references: [], followups: [], warnings: [],
});

const ignoreWorkspaceUpdate = () => {};

const PHASES: Record<string, string> = {
  retrieving: "正在检索", web_search: "正在联网搜索", generating: "正在生成", followups: "正在生成追问",
};

function phaseForStatus(status: ChatMessageStatus | undefined): ChatSessionPhase {
  if (status === "failed") return "FAILED";
  if (status === "stopped") return "STOPPED";
  return "READY";
}

function isLatestUrlEffect(lifecycle: { current: number }, effectId: number): boolean {
  return lifecycle.current === effectId;
}

interface ChatSessionOptions {
  /** Reuse session/stream lifecycle without the main Chat URL, sidebar or draft. */
  embedded?: boolean;
  identityScope: ChatIdentityScope;
  initialSessionId?: string | null;
  /** Reactive App Router identity. `null` is the explicit no-session route. */
  desiredSessionId?: string | null;
  onSessionIdChange?: (id: string | null) => void;
}

interface PendingCreate {
  request: ReturnType<typeof beginTurn>;
  localId: string;
  generation: SessionGenerationHandle;
}

type TurnsUpdater = ChatTurn[] | ((previous: ChatTurn[]) => ChatTurn[]);

export function useChatSession({
  identityScope,
  embedded = false,
  initialSessionId = null,
  desiredSessionId,
  onSessionIdChange,
}: ChatSessionOptions) {
  const pathname = usePathname();
  // This is a mount-time continuity bootstrap only. Runtime route changes are
  // supplied by ChatWorkspace through desiredSessionId, so a render cannot
  // observe window.location before Next's HistoryUpdater commits it.
  const [bootstrapSessionId] = useState<string | null>(
    () => embedded ? null : readCurrentSessionId() ?? initialSessionId ?? null,
  );
  const routeIdentity = desiredSessionId !== undefined
    ? desiredSessionId
    : bootstrapSessionId;
  const [resolvedInitialSessionId, setResolvedInitialSessionId] = useState<string | null>(
    bootstrapSessionId,
  );
  const lastRouteIdentity = useRef<string | null | undefined>(undefined);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [hydrating, setHydrating] = useState(Boolean(bootstrapSessionId));
  const [interactionLocked, setInteractionLocked] = useState(Boolean(bootstrapSessionId));
  const [sessionPreferences, setSessionPreferences] = useState<ChatSessionPreferences | null>(null);
  const [localHistoryId, setLocalHistoryId] = useState<string | null>(null);
  const [hydratingSessionId, setHydratingSessionId] = useState<string | null>(bootstrapSessionId);
  const [phase, setPhase] = useState<ChatSessionPhase>(bootstrapSessionId ? "HYDRATING" : "LANDING");
  const [loadError, setLoadError] = useState<string | null>(null);

  const sessionRef = useRef<string | null>(null);
  const localHistoryIdRef = useRef<string | null>(null);
  const busyRef = useRef(false);
  const hydratingRef = useRef(Boolean(bootstrapSessionId));
  const interactionLockedRef = useRef(Boolean(bootstrapSessionId));
  const abortRef = useRef<AbortController | null>(null);
  const activeGenerationRef = useRef<SessionGenerationHandle | null>(null);
  const generationGateRef = useRef(new SessionGenerationGate());
  const lifecycleEpochRef = useRef(0);
  const currentMessageId = useRef<string | null>(null);
  const lastInput = useRef<ChatSendInput | null>(null);
  const pendingCreate = useRef<PendingCreate | null>(null);
  const turnsRef = useRef<ChatTurn[]>([]);
  const handledUrlSessionId = useRef<string | null | undefined>(undefined);
  const handledPendingActionId = useRef<number | null>(null);
  const urlEffectLifecycle = useRef(0);
  const onSessionIdChangeRef = useRef(onSessionIdChange);
  const pendingAction = useAskSidebarBridge((s) => embedded ? null : s.pendingAction);
  const pendingActionRef = useRef(pendingAction);
  const pathnameRef = useRef(pathname);

  onSessionIdChangeRef.current = onSessionIdChange;
  pendingActionRef.current = pendingAction;
  pathnameRef.current = pathname;

  const setActiveHistoryId = useAskSidebarBridge((s) => embedded ? ignoreWorkspaceUpdate : s.setActiveHistoryId);
  const setActiveSessionId = useAskSidebarBridge((s) => embedded ? ignoreWorkspaceUpdate : s.setActiveSessionId);
  const removeHistoryItem = useAskSidebarBridge((s) => embedded ? ignoreWorkspaceUpdate : s.removeHistoryItem);
  const clearPending = useAskSidebarBridge((s) => embedded ? ignoreWorkspaceUpdate : s.clearPending);
  const bumpHistoryRefresh = useAskSidebarBridge((s) => embedded ? ignoreWorkspaceUpdate : s.bumpHistoryRefresh);

  const setBusyValue = useCallback((value: boolean) => {
    busyRef.current = value;
    setBusy(value);
  }, []);

  const setHydration = useCallback((value: boolean, id: string | null = null) => {
    hydratingRef.current = value;
    setHydrating(value);
    setHydratingSessionId(value ? id : null);
  }, []);

  const setInteraction = useCallback((value: boolean) => {
    interactionLockedRef.current = value;
    setInteractionLocked(value);
  }, []);

  const setLocalId = useCallback((id: string | null) => {
    localHistoryIdRef.current = id;
    setLocalHistoryId(id);
  }, []);

  const setActiveSession = useCallback((id: string | null, syncUrl = true) => {
    sessionRef.current = id;
    setSessionId(id);
    setActiveSessionId(id);
    if (syncUrl) onSessionIdChangeRef.current?.(id);
  }, [setActiveSessionId]);

  const writeTurns = useCallback((updater: TurnsUpdater) => {
    const next = typeof updater === "function" ? updater(turnsRef.current) : updater;
    turnsRef.current = next;
    setTurns(next);
  }, []);

  const patch = useCallback((id: string, data: Partial<ChatTurn>) => {
    writeTurns((previous) => previous.map((turn) => turn.localId === id ? { ...turn, ...data } : turn));
  }, [writeTurns]);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  /**
   * Retire the current owner before a reset, route change, unmount, or new
   * operation. The backend stop is best-effort and has no UI write path.
   */
  const invalidateGeneration = useCallback(({ stopBackend = true }: { stopBackend?: boolean } = {}) => {
    const messageId = currentMessageId.current;
    lifecycleEpochRef.current += 1;
    generationGateRef.current.cancel();
    abortRef.current?.abort();
    abortRef.current = null;
    activeGenerationRef.current = null;
    currentMessageId.current = null;
    pendingCreate.current = null;
    setBusyValue(false);
    setHydration(false);

    if (stopBackend && messageId) {
      // This request only retires the server-side task. Its success and
      // failure deliberately cannot mutate the newly selected session.
      void stopChatMessage(messageId).catch(() => {});
    }
  }, [setBusyValue, setHydration]);

  const startGeneration = useCallback((id: string | null, options?: { stopBackend?: boolean }) => {
    invalidateGeneration(options);
    const generation = generationGateRef.current.begin(id);
    activeGenerationRef.current = generation;
    abortRef.current = generation.controller;
    generation.controller.signal.addEventListener("abort", () => {
      const owned = generationGateRef.current.current() === generation
        && activeGenerationRef.current === generation;
      // Gate cancellation clears ownership before aborting, so retired
      // generations cannot run this callback against a new session.
      if (!owned) return;
      if (!generation.isCurrent() && generationGateRef.current.current() !== generation) return;
      generationGateRef.current.cancel();
      activeGenerationRef.current = null;
      abortRef.current = null;
      currentMessageId.current = null;
      pendingCreate.current = null;
      setBusyValue(false);
      setInteraction(false);
      setPhase("STOPPED");
    }, { once: true });
    return generation;
  }, [invalidateGeneration, setBusyValue, setInteraction]);

  const finishGeneration = useCallback((
    generation: SessionGenerationHandle,
    status?: ChatMessageStatus,
    phaseOverride?: ChatSessionPhase,
  ) => {
    if (!generation.isCurrent()) return false;
    if (!generationGateRef.current.complete(generation)) return false;
    if (activeGenerationRef.current === generation) activeGenerationRef.current = null;
    if (abortRef.current === generation.controller) abortRef.current = null;
    currentMessageId.current = null;
    if (pendingCreate.current?.generation === generation) pendingCreate.current = null;
    setBusyValue(false);
    setHydration(false);
    setInteraction(false);
    setPhase(phaseOverride ?? phaseForStatus(status));
    bumpHistoryRefresh();
    return true;
  }, [bumpHistoryRefresh, setBusyValue, setHydration, setInteraction]);

  const runStream = useCallback(async (
    generation: SessionGenerationHandle,
    messageId: string,
    localId: string,
    cursor?: string,
  ): Promise<ChatMessageStatus | undefined> => {
    const active = () => generation.isCurrent()
      && activeGenerationRef.current === generation
      && abortRef.current === generation.controller;
    if (!active()) return undefined;

    currentMessageId.current = messageId;
    setBusyValue(true);
    setPhase("STREAMING");
    let finalStatus: ChatMessageStatus | undefined;
    try {
      await streamChatMessage(messageId, {
        onMeta: (meta) => {
          if (!active()) return;
          patch(localId, {
            ...(meta.phase ? { thought: PHASES[meta.phase] ?? meta.phase } : {}),
            ...(meta.read_count !== undefined ? { readCount: meta.read_count } : {}),
            ...(meta.knowledge_grounding ? { knowledgeGrounding: meta.knowledge_grounding } : {}),
            ...(meta.warnings ? { warnings: meta.warnings } : {}),
          });
        },
        onDelta: (delta) => {
          if (!active()) return;
          writeTurns((previous) => previous.map((turn) => turn.localId === localId ? {
            ...turn, content: turn.content + (delta.text ?? ""),
            reasoning: turn.reasoning + (delta.reasoning ?? ""),
          } : turn));
        },
        onRefs: ({ references }) => { if (active()) patch(localId, { references }); },
        onFollowups: ({ items }) => { if (active()) patch(localId, { followups: items }); },
        onDone: (done) => {
          if (!active()) return;
          finalStatus = done.status;
          patch(localId, {
            status: done.status,
            durationMs: done.duration_ms,
            thought: "生成结束",
            ...(done.knowledge_grounding ? { knowledgeGrounding: done.knowledge_grounding } : {}),
          });
        },
        onError: (error) => {
          if (!active()) return;
          finalStatus = "failed";
          patch(localId, { status: "failed", error: error.message });
        },
      }, { signal: generation.controller.signal, lastEventId: cursor });
    } catch (error) {
      // Abort is a lifecycle event. Only the current owner may mark a real
      // stream failure, and stale aborts are intentionally silent.
      if (active() && !isAbortError(error)) {
        finalStatus = "failed";
        patch(localId, { status: "failed", error: messageForApiError(error) });
      }
    }
    return finalStatus;
  }, [patch, setBusyValue, writeTurns]);

  /** 仅在后端未分配 session_id 时写入 localStorage。 */
  const persistLocalFallback = useCallback((input: ChatSendInput, nextTurns: ChatTurn[]) => {
    if (embedded || sessionRef.current) return;
    const id = localHistoryIdRef.current ?? `local_${Date.now().toString(36)}`;
    if (!localHistoryIdRef.current) setLocalId(id);
    const firstUser = nextTurns.find((turn) => turn.role === "user");
    upsertLocalAskSession(identityScope, {
      id,
      title: titleFromQuestion(firstUser?.content ?? input.question),
      updatedAt: Date.now(),
      turns: nextTurns,
      mode: input.mode,
      model: input.model,
      web_search: input.web_search,
      knowledge_enabled: input.capabilities.knowledge.enabled,
    });
    bumpHistoryRefresh();
  }, [bumpHistoryRefresh, embedded, identityScope, setLocalId]);

  const send = useCallback(async (input: ChatSendInput) => {
    const question = input.question.trim();
    if (!question || busyRef.current || hydratingRef.current || interactionLockedRef.current) return;

    const generation = startGeneration(sessionRef.current);
    const retiringLocalId = localHistoryIdRef.current;
    setLocalId(null);
    lastInput.current = { ...input, question };
    const user = newTurn("user", question);
    const assistant = newTurn("assistant");
    writeTurns((previous) => [...previous, user, assistant]);
    setBusyValue(true);
    setPhase("STREAMING");

    let finalStatus: ChatMessageStatus | undefined;
    try {
      const request = beginTurn(sessionRef.current, { ...input, question }, { signal: generation.controller.signal });
      pendingCreate.current = { request, localId: assistant.localId, generation };
      const created = await request;
      if (!generation.isCurrent()) {
        await stopChatMessage(created.message_id).catch(() => {});
        return;
      }
      if (pendingCreate.current?.generation === generation) pendingCreate.current = null;
      setActiveSession(created.session_id);
      if (retiringLocalId) deleteLocalAskSession(identityScope, retiringLocalId);
      patch(assistant.localId, { messageId: created.message_id });
      if (!embedded) clearAskDraft();
      finalStatus = await runStream(generation, created.message_id, assistant.localId);
    } catch (error) {
      if (generation.isCurrent() && !isAbortError(error)) {
        finalStatus = "failed";
        patch(assistant.localId, { status: "failed", error: messageForApiError(error) });
        if (!sessionRef.current) persistLocalFallback(input, turnsRef.current);
      }
    } finally {
      if (!generation.isCurrent()) return;
      if (pendingCreate.current?.generation === generation) pendingCreate.current = null;
      finishGeneration(generation, finalStatus ?? "failed");
    }
  }, [embedded, finishGeneration, identityScope, patch, persistLocalFallback, runStream, setActiveSession, setBusyValue, setLocalId, startGeneration, writeTurns]);

  const stop = useCallback(async () => {
    if (!busyRef.current && !pendingCreate.current && !currentMessageId.current) return;

    const messageIdBeforeStop = currentMessageId.current;
    const pendingBeforeStop = pendingCreate.current;
    const generation = startGeneration(sessionRef.current, { stopBackend: false });
    let messageId = messageIdBeforeStop;
    setBusyValue(false);
    setInteraction(true);
    setPhase("STOPPED");
    writeTurns((previous) => previous.map((turn) => turn.status === "streaming"
      ? { ...turn, status: "stopped", thought: "已停止" }
      : turn));

    try {
      if (pendingBeforeStop) {
        try {
          const created = await pendingBeforeStop.request;
          if (!generation.isCurrent()) {
            await stopChatMessage(created.message_id).catch(() => {});
            return;
          }
          messageId = created.message_id;
          setActiveSession(created.session_id);
          patch(pendingBeforeStop.localId, { messageId, status: "stopped" });
        } catch {
          // An aborted create request may never allocate a server message.
        }
      }
      if (generation.isCurrent() && messageId) {
        await stopChatMessage(messageId, { signal: generation.controller.signal });
      }
      if (generation.isCurrent() && lastInput.current && !sessionRef.current) {
        persistLocalFallback(lastInput.current, turnsRef.current);
      }
    } catch (error) {
      if (generation.isCurrent() && !isAbortError(error)) {
        writeTurns((previous) => previous.map((turn) => turn.messageId === messageId
          ? { ...turn, error: `停止请求未确认：${messageForApiError(error)}` } : turn));
      }
    } finally {
      if (!generation.isCurrent()) return;
      finishGeneration(generation, "stopped", "STOPPED");
    }
  }, [finishGeneration, patch, persistLocalFallback, setActiveSession, setBusyValue, setInteraction, startGeneration, writeTurns]);

  const resumeLast = useCallback(async () => {
    if (busyRef.current || hydratingRef.current || interactionLockedRef.current) return;
    const last = turnsRef.current.at(-1);
    if (!last || !["stopped", "failed"].includes(last.status)) return;
    if (!last.messageId) {
      if (lastInput.current) {
        writeTurns((previous) => previous.slice(0, -2));
        await send(lastInput.current);
      }
      return;
    }

    const generation = startGeneration(sessionRef.current);
    const operationEpoch = lifecycleEpochRef.current;
    setBusyValue(true);
    setPhase("STREAMING");
    patch(last.localId, { status: "streaming", error: undefined, thought: "继续生成…" });
    let finalStatus: ChatMessageStatus | undefined;
    let resend: ChatSendInput | null = null;
    try {
      const resumed = await resumeChatMessage(last.messageId, { signal: generation.controller.signal });
      if (!generation.isCurrent()) {
        await stopChatMessage(resumed.message_id).catch(() => {});
        return;
      }
      finalStatus = await runStream(generation, resumed.message_id, last.localId, resumed.last_event_id);
    } catch (error) {
      if (generation.isCurrent() && !isAbortError(error)) {
        if (isMissingSessionError(error) && lastInput.current) {
          patch(last.localId, {
            status: "failed",
            messageId: undefined,
            error: "原回答已失效，请重新发送。",
          });
          writeTurns((previous) => previous.slice(0, -2));
          resend = lastInput.current;
          finalStatus = "failed";
        } else {
          finalStatus = "failed";
          patch(last.localId, { status: "failed", error: messageForApiError(error) });
        }
      }
    } finally {
      if (!generation.isCurrent()) return;
      finishGeneration(generation, finalStatus ?? "failed");
    }

    if (resend && lifecycleEpochRef.current === operationEpoch && sessionRef.current === generation.sessionId) {
      await send(resend);
    }
  }, [finishGeneration, patch, runStream, send, setBusyValue, startGeneration, writeTurns]);

  const reset = useCallback(({ syncUrl = true }: { syncUrl?: boolean } = {}) => {
    setPhase("RESETTING");
    invalidateGeneration();
    setHydration(false);
    setInteraction(false);
    setActiveSession(null, syncUrl);
    setLocalId(null);
    setSessionPreferences(null);
    writeTurns([]);
    lastInput.current = null;
    setLoadError(null);
    setPhase("LANDING");
  }, [invalidateGeneration, setActiveSession, setHydration, setInteraction, setLocalId, writeTurns]);

  const openSession = useCallback(async (id: string) => {
    const generation = startGeneration(id);
    setPhase("HYDRATING");
    setHydration(true, id);
    setInteraction(true);
    setBusyValue(false);
    setActiveSession(null, false);
    setActiveSessionId(id);
    setLocalId(null);
    setSessionPreferences(null);
    writeTurns([]);
    lastInput.current = null;
    setLoadError(null);

    let settled = false;
    try {
      const session = await getChatSession(id, { signal: generation.controller.signal });
      if (!generation.isCurrent()) return undefined;

      const preferences: ChatSessionPreferences = {
        mode: session.mode,
        model: session.model,
        webSearch: session.web_search,
        entryMode: session.capabilities?.knowledge.enabled ? "ai" : "search",
      };
      const restored = restoreTurns(session);
      const latestUser = [...restored].reverse().find((turn) => turn.role === "user");
      setSessionPreferences(preferences);
      writeTurns(restored);
      if (latestUser) {
        lastInput.current = {
          question: latestUser.content,
          mode: preferences.mode,
          model: preferences.model,
          web_search: preferences.webSearch,
          attachments: [],
          capabilities: { knowledge: { enabled: preferences.entryMode === "ai" } },
        };
      }
      // A successful hydration reasserts the canonical URL. This is a no-op
      // for normal URL entry, but repairs a retry after a stale response.
      setActiveSession(id, true);
      settled = finishGeneration(generation, undefined, phaseForRestoredStatus(session.messages.at(-1)?.status));
      return session;
    } catch (error) {
      if (!generation.isCurrent()) return undefined;
      if (isMissingSessionError(error)) {
        settled = finishGeneration(generation, undefined, "STALE");
        setActiveSession(null, false);
        setSessionPreferences(null);
        setLocalId(null);
        writeTurns([]);
        lastInput.current = null;
        removeHistoryItem(id, "db");
        // The 404 branch owns the cleared URL. Mark that identity as handled
        // before replaceState so the URL effect preserves the visible STALE
        // state instead of immediately resetting it to LANDING.
        handledUrlSessionId.current = null;
        onSessionIdChangeRef.current?.(null);
        return undefined;
      }

      settled = finishGeneration(generation, "failed", "FAILED");
      setActiveSession(null, false);
      setSessionPreferences(null);
      setLocalId(null);
      writeTurns([]);
      lastInput.current = null;
      setLoadError(messageForApiError(error));
      return undefined;
    } finally {
      // A current generation must always leave HYDRATING, even if an
      // unexpected future code path exits without settling explicitly.
      if (generation.isCurrent() && !settled) {
        finishGeneration(generation, "failed", "FAILED");
        setLoadError("对话加载失败");
      }
    }
  }, [finishGeneration, removeHistoryItem, setActiveSession, setActiveSessionId, setBusyValue, setHydration, setInteraction, setLocalId, startGeneration, writeTurns]);

  const loadLocalSession = useCallback((item: LocalAskSession) => {
    invalidateGeneration();
    const restored = item.turns.map((turn) => turn.role === "assistant" && turn.status === "streaming"
      ? { ...turn, status: "stopped" as const, thought: "上次生成已中断" }
      : turn);
    setHydration(false);
    setInteraction(false);
    setBusyValue(false);
    setPhase("READY");
    setActiveSession(null, false);
    setLocalId(item.id);
    setSessionPreferences({
      mode: item.mode as ChatReplyMode,
      model: item.model as ChatModelId,
      webSearch: item.web_search,
      entryMode: item.knowledge_enabled ? "ai" : "search",
    });
    writeTurns(restored);
    const firstUser = restored.find((turn) => turn.role === "user");
    lastInput.current = {
      question: firstUser?.content ?? "",
      mode: item.mode as ChatReplyMode,
      model: item.model as ChatModelId,
      web_search: item.web_search,
      attachments: [],
      capabilities: { knowledge: { enabled: item.knowledge_enabled ?? false } },
    };
  }, [invalidateGeneration, setActiveSession, setBusyValue, setHydration, setInteraction, setLocalId, writeTurns]);

  const activeHistoryId = phase === "HYDRATING"
    ? hydratingSessionId
    : sessionId ?? localHistoryId;

  useEffect(() => {
    setActiveHistoryId(activeHistoryId);
  }, [activeHistoryId, setActiveHistoryId]);

  useEffect(() => {
    if (!pendingAction) return;
    if (handledPendingActionId.current === pendingAction.requestId) return;

    if (pendingAction.type === "reset") {
      handledPendingActionId.current = pendingAction.requestId;
      reset();
      clearPending();
      return;
    }
    if (pendingAction.type !== "load") return;
    if (pendingAction.item.source !== "local") {
      // DB history is URL-only; a DB item must never form a second detail-load
      // pathway through the bridge.
      handledPendingActionId.current = pendingAction.requestId;
      clearPending();
      return;
    }
    if (pendingAction.targetPath && pathname !== pendingAction.targetPath) return;
    if (resolvedInitialSessionId) return;

    handledPendingActionId.current = pendingAction.requestId;
    const local = getLocalAskSession(identityScope, pendingAction.item.id);
    if (local) loadLocalSession(local);
    clearPending();
  }, [clearPending, identityScope, loadLocalSession, pathname, pendingAction, reset, resolvedInitialSessionId]);

  useEffect(() => {
    const effectId = ++urlEffectLifecycle.current;
    const isInitialOrStrictReplay = lastRouteIdentity.current === undefined
      || lastRouteIdentity.current === routeIdentity;
    lastRouteIdentity.current = routeIdentity;
    // A live URL written by the mounted workspace can be ahead of the
    // App-Router snapshot during a remount. Use it only for that first
    // bootstrap observation; every later transition comes from the reactive
    // route identity above, including an explicit null reset.
    const urlSessionId = isInitialOrStrictReplay && routeIdentity === null
      ? bootstrapSessionId
      : routeIdentity;
    const action = pendingActionRef.current;
    const pendingLocalAction = action?.type === "load"
      && action.item.source === "local"
      && (!action.targetPath || pathnameRef.current === action.targetPath);

    if (action?.type === "reset") {
      // The explicit reset owns invalidation until the router publishes the
      // cleared URL.
      handledUrlSessionId.current = urlSessionId;
    } else if (!urlSessionId && pendingLocalAction) {
      // Let the local-history bridge consume its action before the no-session
      // URL path resets the newly selected local snapshot.
      handledUrlSessionId.current = urlSessionId;
    } else {
      const transition = transitionSessionNavigation(
        { handledSessionId: handledUrlSessionId.current },
        urlSessionId,
      );
      if (transition.shouldHydrate) {
        handledUrlSessionId.current = transition.state.handledSessionId;
        setResolvedInitialSessionId(urlSessionId);
        if (urlSessionId && urlSessionId === sessionRef.current && !hydratingRef.current) {
          // A newly created session already owns this mounted workspace. The
          // URL remains canonical without starting a duplicate hydration.
        } else if (urlSessionId) {
          void openSession(urlSessionId);
        } else {
          reset({ syncUrl: false });
        }
      }
    }

    return () => {
      // React StrictMode replays effects synchronously. Deferring the cleanup
      // lets the replay advance effectId, while a real unmount still aborts
      // the owner on the next microtask.
      queueMicrotask(() => {
        if (!isLatestUrlEffect(urlEffectLifecycle, effectId)) return;
        handledUrlSessionId.current = undefined;
        invalidateGeneration();
      });
    };
  }, [bootstrapSessionId, invalidateGeneration, openSession, reset, routeIdentity]);

  return {
    sessionId,
    turns,
    busy,
    hydrating,
    interactionLocked,
    sessionPreferences,
    phase,
    loadError,
    send,
    stop,
    resumeLast,
    reset,
    openSession,
    resolvedInitialSessionId,
  };
}
