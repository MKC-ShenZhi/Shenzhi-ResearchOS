import { apiJson, expectedUserHeaders } from "./http";

export type PaperBehaviorType = "paper_impression" | "paper_click" |
  "recommendation_impression" | "recommendation_click" | "search_result_click" |
  "active_read" | "abstract_expand";

/**
 * `userId` is the account the page believes it serves. It is sent only as a
 * precondition so an old tab cannot attribute events to a newly signed-in
 * account; the BFF session alone decides the event owner.
 */
export function recordPaperBehavior(input: {
  userId: string;
  eventType: PaperBehaviorType;
  paperId: string;
  source: "discovery" | "recommendation" | "search" | "paper_detail";
  requestId?: string;
  queryId?: string;
  rank?: number;
  durationSeconds?: number;
}): void {
  if (!input.userId || typeof crypto === "undefined" || !crypto.randomUUID) return;
  void apiJson<{ inserted: number }>("/behavior-events/batch", {
    method: "POST",
    headers: expectedUserHeaders(input.userId),
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

export function recordSearchSubmit(query: string, userId: string): string | null {
  const normalized = query.trim();
  if (!userId || !normalized || normalized.length > 200 || typeof crypto === "undefined" || !crypto.randomUUID) return null;
  const queryId = crypto.randomUUID();
  void apiJson<{ inserted: number }>("/behavior-events/batch", {
    method: "POST",
    headers: expectedUserHeaders(userId),
    body: JSON.stringify({ events: [{
      event_id: queryId, query_id: queryId, event_type: "search_submit",
      query: normalized, source: "search",
    }] }),
  }).catch(() => undefined);
  return queryId;
}
