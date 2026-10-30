import type { ConferenceDeadlineDto } from "../../../clients/backend/conferences";
import { milestoneLabel } from "./deadline-time";

function icsDateTime(date: Date): string {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

/** RFC 5545 TEXT escaping. */
function icsText(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\r?\n/g, "\\n")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,");
}

/** Event title shared by the .ics export and the web-calendar links. */
export function milestoneEventSummary(
  conference: ConferenceDeadlineDto,
  milestone: ConferenceDeadlineDto["edition"]["milestones"][number],
): string {
  return [
    `${conference.title} ${conference.edition.year} ${milestoneLabel(milestone)}`,
    milestone.comment ? `(${milestone.comment})` : "",
  ].filter(Boolean).join(" ");
}

/**
 * One calendar event per upcoming dated milestone of the conference's current edition,
 * each with a reminder one day before. Past and TBD milestones are skipped.
 */
export function buildConferenceIcs(conference: ConferenceDeadlineDto, now: Date): string | null {
  const { edition } = conference;
  const events = edition.milestones.flatMap((milestone, index) => {
    if (!milestone.at) return [];
    const at = new Date(milestone.at);
    if (at.getTime() <= now.getTime()) return [];
    const summary = milestoneEventSummary(conference, milestone);
    return [
      "BEGIN:VEVENT",
      `UID:${icsText(`${conference.id}-${edition.year}-${index}-${milestone.kind}@shenzhi`)}`,
      `DTSTAMP:${icsDateTime(now)}`,
      `DTSTART:${icsDateTime(at)}`,
      `DTEND:${icsDateTime(at)}`,
      `SUMMARY:${icsText(summary)}`,
      `DESCRIPTION:${icsText(conference.description)}`,
      ...(edition.link ? [`URL:${icsText(edition.link)}`] : []),
      "BEGIN:VALARM",
      "ACTION:DISPLAY",
      `DESCRIPTION:${icsText(summary)}`,
      "TRIGGER:-P1D",
      "END:VALARM",
      "END:VEVENT",
    ];
  });
  if (events.length === 0) return null;
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ShenZhi//Conference Deadlines//ZH",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    ...events,
    "END:VCALENDAR",
  ].join("\r\n") + "\r\n";
}
