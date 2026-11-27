import type { AgentChatTurn } from "./session-state";

/** Preserve presentation snapshots alongside the legacy export transcript. */
export function sessionExportMessages(turns: AgentChatTurn[]) {
  return turns.filter((turn) => turn.role === "user" || turn.structured.message
    || turn.content || turn.report || turn.question).map((turn) => turn.role === "user"
    ? { kind: "user", text: turn.content }
    : { kind: "assistant", message: turn.structured.message,
        content: turn.report ?? (turn.content || turn.question?.question || ""),
        reasoning: turn.reasoning || "",
        tool_calls: turn.stream.entries.flatMap((entry) => entry.kind === "tool"
          ? [{ id: entry.tool.toolCallId, name: entry.tool.name, arguments: entry.tool.arguments }] : []),
        stop_reason: "stop" });
}
