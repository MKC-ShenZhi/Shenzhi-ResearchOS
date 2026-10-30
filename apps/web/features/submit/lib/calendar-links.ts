import type { ConferenceDeadlineDto, ConferenceMilestoneDto } from "../../../clients/backend/conferences";
import { formatOfficialTime } from "./deadline-time";
import { milestoneEventSummary } from "./ics";

type DatedMilestone = ConferenceMilestoneDto & { at: string };

/** 事件详情首行放深知会议页链接，日历提醒点开后回到站内 */
function eventDetails(conference: ConferenceDeadlineDto, milestone: DatedMilestone, pageUrl: string): string {
  const { edition } = conference;
  return [
    `在深知查看截稿倒计时：${pageUrl}`,
    conference.description,
    milestone.local ? `官方时间：${formatOfficialTime(milestone.local, edition.timezone)}` : "",
    edition.link ? `会议官网：${edition.link}` : "",
  ].filter(Boolean).join("\n");
}

/** `20261118T115959Z` —— Google Calendar 的 UTC 时间格式 */
function googleDateTime(iso: string): string {
  return new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

/**
 * Google Calendar 预填事件链接。截稿是一个时刻，起止时间相同；
 * 网页日历一次只能预填一个事件，因此只取单个节点。
 */
export function googleCalendarUrl(
  conference: ConferenceDeadlineDto,
  milestone: DatedMilestone,
  pageUrl: string,
): string {
  const at = googleDateTime(milestone.at);
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: milestoneEventSummary(conference, milestone),
    dates: `${at}/${at}`,
    details: eventDetails(conference, milestone, pageUrl),
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

/** Outlook 网页版预填事件链接；`outlook.live.com` 为个人账户，`outlook.office.com` 为工作/学校账户。 */
export function outlookCalendarUrl(
  conference: ConferenceDeadlineDto,
  milestone: DatedMilestone,
  pageUrl: string,
  host: "outlook.live.com" | "outlook.office.com" = "outlook.live.com",
): string {
  const at = new Date(milestone.at).toISOString();
  const params = new URLSearchParams({
    path: "/calendar/action/compose",
    rru: "addevent",
    subject: milestoneEventSummary(conference, milestone),
    startdt: at,
    enddt: at,
    body: eventDetails(conference, milestone, pageUrl),
  });
  return `https://${host}/calendar/0/deeplink/compose?${params.toString()}`;
}
