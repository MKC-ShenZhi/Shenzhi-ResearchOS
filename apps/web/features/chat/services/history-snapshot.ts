import type { ChatSessionSummary } from "@/types/ai-search";
import type { SidebarChatHistoryItem } from "@/stores/ask-sidebar-bridge";
import type { LocalAskSession } from "./local-history";

type BackendHistoryRecord = Pick<ChatSessionSummary, "id" | "title" | "updated_at" | "favorite">;

/** Merge the authoritative backend list with separately owned local fallback entries. */
export function mergeHistorySources(
  db: BackendHistoryRecord[],
  local: LocalAskSession[],
): SidebarChatHistoryItem[] {
  return [
    ...db.map((session) => ({
      id: session.id,
      title: session.title,
      // Backend Chat timestamps are Unix seconds; browser Date APIs use ms.
      updatedAt: session.updated_at * 1000,
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
