import { apiJson } from "./http";

export type PaperBehaviorType = "paper_impression" | "paper_click" |
  "recommendation_impression" | "recommendation_click" | "search_result_click" |
  "active_read" | "abstract_expand";

export function recordPaperBehavior(input: {
  eventType: PaperBehaviorType;
  paperId: string;
  source: "discovery" | "recommendation" | "search" | "paper_detail";
  requestId?: string;
  queryId?: string;
  rank?: number;
  durationSeconds?: number;
}): void {
  if (typeof crypto === "undefined" || !crypto.randomUUID) return;
  void apiJson<{ inserted: number }>("/behavior-events/batch", {
    method: "POST",
    body: JSON.stringify({ events: [{
      event_id: crypto.randomUUID(),
      event_type: input.eventType,
      paper_id: input.paperId,
      source: input.source,
      request_id: input.requestId,
      query_id: input.queryId,
      rank: input.rank,
      duration_seconds: input.eventType === "active_read" && input.durationSeconds !== undefined
        ? Math.floor(input.durationSeconds)
        : input.durationSeconds,
    }] }),
  }).catch(() => undefined);
}

export function recordSearchSubmit(query: string): string | null {
  const normalized = query.trim();
  if (!normalized || normalized.length > 200 || typeof crypto === "undefined" || !crypto.randomUUID) return null;
  const queryId = crypto.randomUUID();
  void apiJson<{ inserted: number }>("/behavior-events/batch", {
    method: "POST",
    body: JSON.stringify({ events: [{
      event_id: queryId, query_id: queryId, event_type: "search_submit",
      query: normalized, source: "search",
    }] }),
  }).catch(() => undefined);
  return queryId;
}
