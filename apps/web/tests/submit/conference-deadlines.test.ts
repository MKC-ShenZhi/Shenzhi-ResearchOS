import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  conferenceDeadlineSearchParams,
  type ConferenceDeadlineDto,
} from "../../clients/backend/conferences";
import {
  compactTimeline,
  deadlineUrgency,
  formatInstant,
  formatOfficialTime,
  remainingUntil,
  upcomingMilestone,
} from "../../features/submit/lib/deadline-time";
import { googleCalendarUrl, outlookCalendarUrl } from "../../features/submit/lib/calendar-links";
import { buildConferenceIcs } from "../../features/submit/lib/ics";
import {
  EMPTY_CONFERENCE_FILTERS,
  RANK_CHIPS,
  hasActiveFilters,
  isRankChipActive,
  toDeadlineQuery,
  toggleCategory,
  toggleRankChip,
} from "../../features/submit/services/conference-filters";

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

function conference(overrides: Partial<ConferenceDeadlineDto> = {}): ConferenceDeadlineDto {
  return {
    id: "ai-aaai",
    title: "AAAI",
    description: "AAAI Conference on Artificial Intelligence; main track",
    category: "AI",
    dblp: "aaai",
    rank: { ccf: "A", core: "A*", thcpl: "A" },
    status: "open",
    next_milestone: null,
    last_deadline_at: "2026-11-18T11:59:59Z",
    edition: {
      year: 2027,
      link: "https://aaai.org/conference/aaai/aaai-27/",
      timezone: "AoE",
      date: null,
      place: null,
      milestones: [
        { kind: "abstract", at: "2026-11-11T11:59:59Z", local: "2026-11-10 23:59:59", comment: null },
        { kind: "full", at: "2026-11-18T11:59:59Z", local: "2026-11-17 23:59:59", comment: null },
        { kind: "full", at: null, local: null, comment: "rebuttal" },
      ],
    },
    edition_count: 6,
    ...overrides,
  };
}

test("remainingUntil splits time left and clamps at zero", () => {
  assert.deepEqual(remainingUntil(2 * DAY + 3 * HOUR + 4 * 60_000 + 5_000, 0), {
    days: 2, hours: 3, minutes: 4, seconds: 5,
  });
  assert.deepEqual(remainingUntil(0, 10_000), { days: 0, hours: 0, minutes: 0, seconds: 0 });
});

test("deadlineUrgency uses inclusive day / week / month thresholds", () => {
  assert.equal(deadlineUrgency(0, 0), "passed");
  assert.equal(deadlineUrgency(DAY, 0), "day");
  assert.equal(deadlineUrgency(DAY + 1, 0), "week");
  assert.equal(deadlineUrgency(7 * DAY, 0), "week");
  assert.equal(deadlineUrgency(30 * DAY, 0), "month");
  assert.equal(deadlineUrgency(30 * DAY + 1, 0), "later");
});

test("upcomingMilestone rolls from abstract to full deadline and ignores TBD", () => {
  const { milestones } = conference().edition;
  assert.equal(upcomingMilestone(milestones, Date.parse("2026-11-01T00:00:00Z")), milestones[0]);
  assert.equal(upcomingMilestone(milestones, Date.parse("2026-11-11T11:59:59Z")), milestones[1]);
  assert.equal(upcomingMilestone(milestones, Date.parse("2026-12-01T00:00:00Z")), null);
});

test("compactTimeline collapses passed rounds and caps upcoming ones, keeping TBD", () => {
  const rounds = Array.from({ length: 10 }, (_, month) => ({
    at: new Date(Date.UTC(2026, month, 1)).toISOString(),
  }));
  const timeline = compactTimeline([...rounds, { at: null }], Date.UTC(2026, 4, 15), 3);
  assert.equal(timeline.passedCount, 5);
  assert.deepEqual(timeline.visible, [rounds[5], rounds[6], rounds[7], { at: null }]);
  assert.equal(timeline.hiddenUpcomingCount, 2);
});

test("formatInstant renders the instant in the requested timezone with a UTC offset", () => {
  assert.equal(formatInstant("2026-11-18T11:59:59Z", "Asia/Shanghai"), "2026-11-18 19:59 (UTC+8)");
  assert.equal(formatInstant("2026-11-18T11:59:59Z", "UTC"), "2026-11-18 11:59 (UTC)");
  assert.equal(formatInstant("2026-11-18T11:59:59Z", "Asia/Kolkata"), "2026-11-18 17:29 (UTC+5:30)");
  assert.equal(formatOfficialTime("2026-11-17 23:59:59", "AoE"), "2026-11-17 23:59 AoE");
});

test("ICS export contains only upcoming dated milestones with escaped text", () => {
  const ics = buildConferenceIcs(conference(), new Date("2026-11-12T00:00:00Z"));
  assert.ok(ics);
  assert.equal(ics.match(/BEGIN:VEVENT/g)?.length, 1);
  assert.match(ics, /DTSTART:20261118T115959Z\r\n/);
  assert.match(ics, /SUMMARY:AAAI 2027 全文截稿\r\n/);
  assert.match(ics, /DESCRIPTION:AAAI Conference on Artificial Intelligence\\; main track\r\n/);
  assert.match(ics, /TRIGGER:-P1D/);
  assert.ok(ics.endsWith("END:VCALENDAR\r\n"));

  assert.equal(buildConferenceIcs(conference(), new Date("2026-12-01T00:00:00Z")), null);
});

test("web calendar links prefill one milestone with title, UTC time and official time", () => {
  const next = conference().edition.milestones[1] as ConferenceDeadlineDto["edition"]["milestones"][number] & { at: string };

  const google = new URL(googleCalendarUrl(conference(), next));
  assert.equal(google.origin + google.pathname, "https://calendar.google.com/calendar/render");
  assert.equal(google.searchParams.get("action"), "TEMPLATE");
  assert.equal(google.searchParams.get("text"), "AAAI 2027 全文截稿");
  assert.equal(google.searchParams.get("dates"), "20261118T115959Z/20261118T115959Z");
  assert.match(google.searchParams.get("details") ?? "", /官方时间：2026-11-17 23:59 AoE/);
  assert.match(google.searchParams.get("details") ?? "", /会议官网：https:\/\/aaai\.org/);

  const outlook = new URL(outlookCalendarUrl(conference(), next));
  assert.equal(outlook.host, "outlook.live.com");
  assert.equal(outlook.searchParams.get("subject"), "AAAI 2027 全文截稿");
  assert.equal(outlook.searchParams.get("startdt"), "2026-11-18T11:59:59.000Z");
  assert.equal(new URL(outlookCalendarUrl(conference(), next, "outlook.office.com")).host, "outlook.office.com");
});

test("filters toggle rank chips per system and hide closed venues by default", () => {
  const ccfA = RANK_CHIPS.find((chip) => chip.label === "CCF-A")!;
  const coreAStar = RANK_CHIPS.find((chip) => chip.label === "CORE-A*")!;
  let state = toggleRankChip(EMPTY_CONFERENCE_FILTERS, ccfA);
  state = toggleRankChip(state, coreAStar);
  state = toggleCategory(state, "AI");
  assert.equal(isRankChipActive(state, ccfA), true);
  assert.equal(hasActiveFilters(state), true);
  assert.deepEqual(toDeadlineQuery({ ...state, q: "  neurips " }), {
    categories: ["AI"],
    ccf: ["A"],
    core: ["A*"],
    thcpl: [],
    statuses: ["open", "tbd"],
    q: "neurips",
  });

  const reverted = toggleRankChip(state, ccfA);
  assert.deepEqual(reverted.ccf, []);
  assert.deepEqual(toDeadlineQuery({ ...EMPTY_CONFERENCE_FILTERS, includeClosed: true }).statuses, []);
  assert.equal(hasActiveFilters(EMPTY_CONFERENCE_FILTERS), false);
});

test("query string repeats list params in a stable order for cache keys", () => {
  const params = conferenceDeadlineSearchParams({
    categories: ["NW", "AI", "AI"],
    ccf: ["B", "A"],
    core: ["A*"],
    statuses: ["tbd", "open"],
    q: " ",
  });
  assert.equal(
    params.toString(),
    "category=AI&category=NW&ccf=A&ccf=B&core=A*&status=open&status=tbd",
  );
});

test("/submit renders the API-backed conference browser, not prototype data", () => {
  const page = readFileSync("features/submit/SubmitPage.tsx", "utf8");
  const data = readFileSync("features/submit/data.ts", "utf8");
  assert.match(page, /<ConferenceBrowser \/>/);
  assert.doesNotMatch(data, /kind: "conference"/);
  assert.doesNotMatch(data, /offsetMs/);
});
