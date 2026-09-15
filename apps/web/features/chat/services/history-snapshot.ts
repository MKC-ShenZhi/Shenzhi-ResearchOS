import type { ChatSessionSummary } from "@/types/ai-search";
import type { SidebarChatHistoryItem } from "@/stores/ask-sidebar-bridge";
import type { LocalAskSession } from "./local-history";

type BackendHistoryRecord = Pick<ChatSessionSummary, "id" | "title" | "updated_at" | "favorite">;

/** Backend `updated_at` is Unix seconds; local fallback uses `Date.now()` milliseconds. */
export function chatTimestampMs(value: number): number {
  return value > 0 && value < 1e12 ? value * 1000 : value;
}

/** Merge the authoritative backend list with separately owned local fallback entries. */
export function mergeHistorySources(
  db: BackendHistoryRecord[],
  local: LocalAskSession[],
): SidebarChatHistoryItem[] {
  return [
    ...db.map((session) => ({
      id: session.id,
      title: session.title,
      updatedAt: chatTimestampMs(session.updated_at),
      source: "db" as const,
      favorite: session.favorite,
    })),
    ...local.map((session) => ({
      id: session.id,
      title: session.title,
      updatedAt: session.updatedAt,
      source: "local" as const,
    })),
  ].sort((a, b) => b.updatedAt - a.updatedAt);
}
