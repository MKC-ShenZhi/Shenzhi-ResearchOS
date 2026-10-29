import type { ConferenceMilestoneDto } from "../../../clients/backend/conferences";

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export interface Remaining {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}

/** Time left until `atMs`, clamped at zero. */
export function remainingUntil(atMs: number, nowMs: number): Remaining {
  const total = Math.max(0, atMs - nowMs);
  return {
    days: Math.floor(total / DAY),
    hours: Math.floor((total % DAY) / HOUR),
    minutes: Math.floor((total % HOUR) / MINUTE),
    seconds: Math.floor((total % MINUTE) / SECOND),
  };
}

export type DeadlineUrgency = "passed" | "day" | "week" | "month" | "later";

/** Thresholds are inclusive: exactly 24h left is still `day`. */
export function deadlineUrgency(atMs: number, nowMs: number): DeadlineUrgency {
  const left = atMs - nowMs;
  if (left <= 0) return "passed";
  if (left <= DAY) return "day";
  if (left <= 7 * DAY) return "week";
  if (left <= 30 * DAY) return "month";
  return "later";
}

/**
 * The next dated milestone after `nowMs`. Re-derived on the client so that an
 * open page rolls over from abstract to full-paper deadline without a refetch.
 */
export function upcomingMilestone<T extends Pick<ConferenceMilestoneDto, "at">>(
  milestones: readonly T[],
  nowMs: number,
): (T & { at: string }) | null {
  let best: (T & { at: string }) | null = null;
  for (const milestone of milestones) {
    if (!milestone.at) continue;
    const atMs = Date.parse(milestone.at);
    if (atMs > nowMs && (!best || atMs < Date.parse(best.at))) best = milestone as T & { at: string };
  }
  return best;
}

export interface CompactTimeline<T> {
  passedCount: number;
  visible: T[];
  hiddenUpcomingCount: number;
}

/**
 * Rolling-deadline venues (e.g. VLDB: monthly) publish a dozen rounds per edition.
 * Collapse passed rounds into a count, show the next `maxUpcoming` dated rounds, keep TBD.
 */
export function compactTimeline<T extends Pick<ConferenceMilestoneDto, "at">>(
  milestones: readonly T[],
  nowMs: number,
  maxUpcoming = 4,
): CompactTimeline<T> {
  const passed = milestones.filter((item) => item.at !== null && Date.parse(item.at) <= nowMs);
  const upcoming = milestones.filter((item) => item.at !== null && Date.parse(item.at) > nowMs);
  const tbd = milestones.filter((item) => item.at === null);
  return {
    passedCount: passed.length,
    visible: [...upcoming.slice(0, maxUpcoming), ...tbd],
    hiddenUpcomingCount: Math.max(0, upcoming.length - maxUpcoming),
  };
}

export function milestoneLabel(milestone: Pick<ConferenceMilestoneDto, "kind">): string {
  return milestone.kind === "abstract" ? "摘要截止" : "全文截稿";
}

// Constructing Intl formatters is costly and countdowns re-render every second.
const formatters = new Map<string, Intl.DateTimeFormat>();

function parts(date: Date, timeZone: string | undefined) {
  const key = timeZone ?? "";
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZoneName: "longOffset",
    });
    formatters.set(key, formatter);
  }
  return Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
}

/**
 * `2026-11-02 09:00 (UTC+8)` in the viewer's timezone (or `timeZone` when given).
 * Deadlines are absolute instants, so the viewer sees their own wall clock.
 */
export function formatInstant(iso: string, timeZone?: string): string {
  const p = parts(new Date(iso), timeZone);
  // longOffset renders `GMT+08:00` / `GMT`; show the shorter `UTC+8` / `UTC+5:30`.
  const match = /^GMT(?:([+-])(\d{2}):(\d{2}))?$/.exec(p.timeZoneName ?? "");
  const offset = !match || !match[1] || (match[2] === "00" && match[3] === "00")
    ? "UTC"
    : `UTC${match[1]}${Number(match[2])}${match[3] === "00" ? "" : `:${match[3]}`}`;
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} (${offset})`;
}

/** Official time as published, e.g. `2026-11-01 17:00 PT`. */
export function formatOfficialTime(local: string, timezone: string): string {
  return `${local.slice(0, 16)} ${timezone}`;
}
