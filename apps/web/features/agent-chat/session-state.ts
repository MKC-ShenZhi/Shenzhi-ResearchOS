/** Session hydration data, without React or renderer dependencies. */
import type { AgentQuestion, AgentStoredTurn } from "../../clients/backend/agent";
import type { ComposerAttachment } from "../../types/ai-search";
import { initialStreamState, type Entry, type StreamState } from "./timeline";
import { initialMessageState, reconcileMessage, type AgentMessageState } from "./message-state";

export interface AgentChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  attachments?: ComposerAttachment[];
  reasoning: string;
  stream: StreamState;
  structured: AgentMessageState;
  steers: Array<{ text: string; kind: "steer" | "follow_up" | "system" }>;
  report?: string;
  sources?: Array<{ title?: string; url?: string }>;
  question?: AgentQuestion;
  warnings?: string[];
  error?: string;
  stopped?: boolean;
  stopReason?: string;
  status?: AgentStoredTurn["status"];
}

function fromStoredTurn(turn: AgentStoredTurn): StreamState {
  const entries: Entry[] = (turn.process ?? []).map((segment) => segment.kind === "tool"
    ? { kind: "tool", tool: segment.tool }
    : { kind: segment.kind === "text" ? "text" : "thinking", text: segment.text });
  return { ...initialStreamState(), entries, runStartIndex: entries.length };
}

export function storedTurns(turns: AgentStoredTurn[]): AgentChatTurn[] {
  return turns.flatMap((turn) => [
    { id: `${turn.id}:user`, role: "user" as const, content: turn.user_content, reasoning: "",
      attachments: (turn.settings.attachments ?? []) as ComposerAttachment[],
      stream: initialStreamState(), structured: initialMessageState(), steers: [] },
    { id: `${turn.id}:assistant`, role: "assistant" as const, content: turn.assistant_content,
      reasoning: turn.reasoning ?? "", stream: fromStoredTurn(turn),
      structured: reconcileMessage(initialMessageState(), turn.message),
      steers: turn.steers ?? [], report: turn.report ?? undefined,
      sources: turn.sources, question: turn.question ?? undefined,
      warnings: turn.warnings, error: turn.error ?? undefined,
      stopped: turn.stopped, stopReason: turn.stop_reason ?? undefined, status: turn.status },
  ]);
}
