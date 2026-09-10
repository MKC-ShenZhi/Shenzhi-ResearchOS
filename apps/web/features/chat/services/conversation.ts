import { createChatSession, sendChatMessage } from "../../../clients/backend/chat";
import type {
  ChatCapabilities,
  ChatSessionDetail,
  ComposerSubmitPayload,
} from "../../../types/ai-search";
import type { ComposerEntryMode } from "../../../types";
import type { ChatSendInput, ChatTurn } from "../types";
import { restoredTurnStatus } from "./session-hydration";

/** Session/message orchestration; HTTP/SSE stays in clients/backend. */
export function beginTurn(sessionId: string | null, input: ChatSendInput, init?: RequestInit) {
  return sessionId
    ? sendChatMessage(sessionId, input, init)
    : createChatSession({ type: "chat", ...input }, init);
}

/** UI-only adapter: the Chat domain receives the nested capability contract. */
export function capabilitiesForEntryMode(entryMode: ComposerEntryMode, knowledgeEnabled?: boolean): ChatCapabilities {
  return { knowledge: { enabled: knowledgeEnabled ?? entryMode === "ai" } };
}

export function chatInputFromComposer(payload: ComposerSubmitPayload): ChatSendInput {
  const { entryMode, knowledgeEnabled, ...input } = payload;
  return { ...input, capabilities: capabilitiesForEntryMode(entryMode, knowledgeEnabled) };
}

export function restoreTurns(session: ChatSessionDetail): ChatTurn[] {
  return session.messages.flatMap((message) => {
    const base = { reasoning: "", thought: "", references: [], followups: [], warnings: [] };
    const knowledgeGrounding = message.knowledge_grounding;
    const status = restoredTurnStatus(message.status);
    return [
      { ...base, localId: `${message.id}-user`, role: "user", content: message.question, status: "done" },
      { ...base, localId: message.id, role: "assistant", messageId: message.id,
        content: message.content, reasoning: message.reasoning, status,
        ...(message.last_event_id ? { lastEventId: message.last_event_id } : {}),
        ...(message.status === "streaming" ? { resumeFromStreaming: true } : {}),
        references: message.references ?? [],
        ...(knowledgeGrounding === undefined || knowledgeGrounding === "grounded"
          ? { readCount: (message.references ?? []).length }
          : {}),
        followups: message.followups ?? [], warnings: message.warnings ?? [],
        durationMs: message.duration_ms, error: message.error ?? undefined,
        ...(knowledgeGrounding ? { knowledgeGrounding } : {}), },
    ];
  });
}
