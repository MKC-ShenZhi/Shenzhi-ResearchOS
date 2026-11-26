/** Pure Block assembly; separate from the legacy reasoning/tool timeline. */
import type { AgentMessage, AgentMessageEvent } from "../../clients/backend/agent-message";
import { isMarkdownBlock } from "../../clients/backend/agent-message";

export interface AgentMessageState {
  runId: string | null;
  message: AgentMessage | null;
  activeBlockId: string | null;
  ended: boolean;
  lastEventId: string | null;
  /** Bad associations/order never erase valid content; a final snapshot repairs state. */
  protocolError: string | null;
}

export function initialMessageState(): AgentMessageState {
  return { runId: null, message: null, activeBlockId: null, ended: false, lastEventId: null, protocolError: null };
}

export function startMessageRun(state: AgentMessageState, runId: string): AgentMessageState {
  // Backend and Runtime can both publish run_start for the same attempt.
  return state.runId === runId ? state : { ...initialMessageState(), runId };
}

function isReplayed(previous: string | null, next: string | undefined): boolean {
  if (previous === null || next === undefined) return false;
  if (previous === next) return true;
  return /^\d+$/.test(previous) && /^\d+$/.test(next) && BigInt(next) <= BigInt(previous);
}

export function reconcileMessage(state: AgentMessageState, message: AgentMessage | null | undefined): AgentMessageState {
  // A legacy result or a transport interruption cannot invalidate generated blocks.
  if (message == null) return state;
  return { ...state, message: structuredClone(message), activeBlockId: null,
    ended: message.status !== "running", protocolError: null };
}

export function applyMessageEvent(state: AgentMessageState, event: AgentMessageEvent): AgentMessageState {
  if (isReplayed(state.lastEventId, event.id)) return state;
  const next = { ...state, lastEventId: event.id ?? state.lastEventId };
  if (event.event === "message_start") {
    return { ...next, message: structuredClone(event.data.message), activeBlockId: null, ended: false, protocolError: null };
  }
  const messageId = "message" in event.data ? event.data.message.id : event.data.message_id;
  if (state.message !== null && state.message.id !== messageId) return state;
  if (event.event === "message_end") return reconcileMessage(next, event.data.message);
  if (state.message === null || state.ended) return state;

  const message = state.message;
  const invalid = (reason: string): AgentMessageState => ({ ...next, protocolError: reason });
  switch (event.event) {
    case "block_start": {
      if (message.blocks.some((block) => block.id === event.data.block.id)) return next;
      if (state.activeBlockId !== null) return invalid("A block is already open");
      return { ...next, activeBlockId: event.data.block.id,
        message: { ...message, blocks: [...message.blocks, structuredClone(event.data.block)] } };
    }
    case "block_delta": {
      if (state.activeBlockId !== event.data.block_id) return invalid("Delta does not target the open block");
      return { ...next, message: { ...message, blocks: message.blocks.map((block) =>
        block.id === event.data.block_id && isMarkdownBlock(block)
          ? { ...block, content: block.content + event.data.delta } : block) } };
    }
    case "block_end":
      if (state.activeBlockId !== event.data.block_id) return invalid("End does not target the open block");
      return { ...next, activeBlockId: null };
    case "reference_upsert": {
      const reference = structuredClone(event.data.reference);
      const exists = message.references.some((item) => item.id === reference.id);
      return { ...next, message: { ...message, references: exists
        ? message.references.map((item) => item.id === reference.id ? reference : item)
        : [...message.references, reference] } };
    }
  }
}
