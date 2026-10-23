import type { KnowledgeConference } from "../../../../clients/knowledge/types";

// Exact upstream names only: aliases are deliberately not merged.
export const FEATURED_CONFERENCES = ["AAAI", "CVPR", "ICML", "ACL", "NeurIPS", "ICLR"] as const;
export const CONFERENCE_PAGE_SIZE = 21;
export const PAPER_BROWSE_PAGE_SIZE = 20;
export const CONFERENCE_BATCH_SIZE = 6;
export const CONFERENCE_ROTATION_MS = 15_000;
export const CONFERENCE_SELECTION_FEEDBACK_MS = 800;

/** Stable batches of browsable records; preserve aliases and duplicate names. */
export function buildConferenceBatches(items: KnowledgeConference[]) {
  const available = items.map((conference, index) => ({ conference, key: `${index}:${conference.name}` }))
    .filter(({ conference }) => conference.paperCount > 0 && conference.years.length > 0);
  const featured = FEATURED_CONFERENCES.flatMap((name) => {
    const match = available.find(({ conference }) => conference.name === name);
    return match ? [match] : [];
  });
  const featuredKeys = new Set(featured.map(({ key }) => key));
  const remaining = available.filter(({ key }) => !featuredKeys.has(key))
    .sort((a, b) => b.conference.paperCount - a.conference.paperCount || a.conference.name.localeCompare(b.conference.name, "en") || a.key.localeCompare(b.key, "en"));
  const ordered = [...featured, ...remaining];
  const batches: typeof ordered[] = [];
  for (let index = 0; index < ordered.length; index += CONFERENCE_BATCH_SIZE) {
    batches.push(ordered.slice(index, index + CONFERENCE_BATCH_SIZE));
  }
  return batches;
}

interface Params { get(name: string): string | null }

function positiveInteger(value: string | null, fallback: number): number {
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : fallback;
}

export function readPaperBrowseState(params: Params) {
  return {
    mode: params.get("mode") === "keyword" || (params.get("mode") !== "conference" && Boolean(params.get("q")?.trim())) ? "keyword" : "conference",
    conference: params.get("conference")?.trim() ?? "",
    year: positiveInteger(params.get("year"), 0),
    page: Math.min(positiveInteger(params.get("page"), 1), Math.floor(2_147_483_647 / PAPER_BROWSE_PAGE_SIZE) + 1),
  };
}

export function resolveConference(items: KnowledgeConference[], name: string) {
  // An explicit unknown name must not silently select a different conference.
  if (name) return items.find((item) => item.name === name);
  return FEATURED_CONFERENCES.map((featured) => items.find((item) => item.name === featured && item.paperCount > 0 && item.years.length > 0)).find(Boolean)
    ?? items.find((item) => item.paperCount > 0 && item.years.length > 0);
}

export function resolveConferenceYear(conference: KnowledgeConference, year: number) {
  return conference.years.includes(year) ? year : (conference.years[0] ?? 0);
}

export function buildPaperBrowseUrl(conference: string, year: number, page = 1) {
  const params = new URLSearchParams({ mode: "conference", conference, year: String(year) });
  if (page > 1) params.set("page", String(page));
  return `/knowledge/search?${params}`;
}

export function readConferenceDirectoryState(params: Params) {
  return {
    query: params.get("q") ?? "",
    year: positiveInteger(params.get("year"), 0),
    sort: params.get("sort") === "name" ? "name" as const : "count" as const,
    page: positiveInteger(params.get("page"), 1),
  };
}

export type ConferenceDirectoryState = ReturnType<typeof readConferenceDirectoryState>;

export function buildConferenceDirectoryUrl(state: ConferenceDirectoryState) {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.year) params.set("year", String(state.year));
  if (state.sort !== "count") params.set("sort", state.sort);
  if (state.page > 1) params.set("page", String(state.page));
  return `/knowledge/search/conferences${params.size ? `?${params}` : ""}`;
}

export function filterConferences(items: KnowledgeConference[], state: ConferenceDirectoryState) {
  const query = state.query.trim().toLocaleLowerCase();
  return items.filter((item) => item.name.toLocaleLowerCase().includes(query) && (!state.year || item.years.includes(state.year)))
    .sort((a, b) => (state.sort === "count" ? b.paperCount - a.paperCount : 0) || a.name.localeCompare(b.name, "en"));
}
