import { apiJson, ApiError, expectedUserHeaders } from "./http";

export type CcfRank = "A" | "B" | "C";
export type CoreRank = "A*" | "A" | "B" | "C";
export type ThcplRank = "A" | "B" | "C";
/** `N` selects venues that are not ranked by that system. */
export type RankFilterValue<T extends string> = T | "N";
export type ConferenceDeadlineStatus = "open" | "tbd" | "closed";

export interface ConferenceRankDto {
  ccf: CcfRank | null;
  core: CoreRank | null;
  thcpl: ThcplRank | null;
}

export interface ConferenceMilestoneDto {
  kind: "abstract" | "full";
  /** Absolute instant (ISO 8601, UTC); null = not announced yet. */
  at: string | null;
  /** Official wall-clock time in `edition.timezone`, as published. */
  local: string | null;
  comment: string | null;
}

export interface ConferenceEditionDto {
  year: number;
  link: string | null;
  timezone: string;
  date: string | null;
  place: string | null;
  milestones: ConferenceMilestoneDto[];
}

export interface ConferenceDeadlineDto {
  id: string;
  title: string;
  description: string;
  category: string;
  dblp: string | null;
  rank: ConferenceRankDto;
  status: ConferenceDeadlineStatus;
  next_milestone: ConferenceMilestoneDto | null;
  last_deadline_at: string | null;
  edition: ConferenceEditionDto;
  edition_count: number;
}

export interface ConferenceDeadlineListDto {
  snapshot_id: string;
  data_as_of: string;
  source_url: string;
  generated_at: string;
  total: number;
  items: ConferenceDeadlineDto[];
}

export interface ConferenceCategoryDto {
  id: string;
  name: string;
  name_en: string | null;
  count: number;
}

export interface ConferenceCategoryListDto {
  snapshot_id: string;
  items: ConferenceCategoryDto[];
}

export interface ConferenceDeadlineQuery {
  categories?: readonly string[];
  ccf?: readonly RankFilterValue<CcfRank>[];
  core?: readonly RankFilterValue<CoreRank>[];
  thcpl?: readonly RankFilterValue<ThcplRank>[];
  statuses?: readonly ConferenceDeadlineStatus[];
  q?: string;
  /** 仅返回当前登录用户关注的会议（需要登录） */
  followed?: boolean;
}

export function conferenceDeadlineSearchParams(query: ConferenceDeadlineQuery): URLSearchParams {
  const params = new URLSearchParams();
  const append = (name: string, values: readonly string[] | undefined) => {
    for (const value of [...new Set(values ?? [])].sort()) params.append(name, value);
  };
  append("category", query.categories);
  append("ccf", query.ccf);
  append("core", query.core);
  append("thcpl", query.thcpl);
  append("status", query.statuses);
  const q = query.q?.trim();
  if (q) params.set("q", q);
  if (query.followed) params.set("followed", "true");
  return params;
}

export async function fetchConferenceDeadlines(
  query: ConferenceDeadlineQuery,
  signal?: AbortSignal,
): Promise<ConferenceDeadlineListDto> {
  const search = conferenceDeadlineSearchParams(query).toString();
  return apiJson<ConferenceDeadlineListDto>(`/conferences${search ? `?${search}` : ""}`, { signal });
}

export async function fetchConferenceCategories(
  signal?: AbortSignal,
): Promise<ConferenceCategoryListDto> {
  return apiJson<ConferenceCategoryListDto>("/conferences/categories", { signal });
}

export interface ConferenceFollowStateDto {
  conference_id: string;
  is_following: boolean;
}

export async function followConference(conferenceId: string, userId: string): Promise<ConferenceFollowStateDto> {
  return apiJson<ConferenceFollowStateDto>(`/conferences/${encodeURIComponent(conferenceId)}/follow`, {
    method: "PUT",
    headers: expectedUserHeaders(userId),
  });
}

export async function unfollowConference(conferenceId: string, userId: string): Promise<ConferenceFollowStateDto> {
  return apiJson<ConferenceFollowStateDto>(`/conferences/${encodeURIComponent(conferenceId)}/follow`, {
    method: "DELETE",
    headers: expectedUserHeaders(userId),
  });
}

export function conferenceQueryRetry(failureCount: number, error: unknown): boolean {
  return failureCount < 1 && error instanceof ApiError && error.status >= 500;
}
