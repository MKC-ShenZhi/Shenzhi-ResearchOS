"use client";

import { cn } from "@/lib/utils";
import type { ConferenceDeadlineDto } from "@/clients/backend/conferences";
import {
  deadlineUrgency,
  formatInstant,
  formatOfficialTime,
  milestoneLabel,
  remainingUntil,
  upcomingMilestone,
  type DeadlineUrgency,
} from "@/features/submit/lib/deadline-time";
import { useNow } from "@/features/submit/hooks/use-now";

const UNITS = ["天", "小时", "分钟", "秒"] as const;

const URGENCY_STYLE: Record<Exclude<DeadlineUrgency, "passed">, { label: string; pill: string; digits: string }> = {
  day: { label: "24 小时内", pill: "bg-danger-soft text-danger", digits: "text-danger" },
  week: {
    label: "本周截止",
    pill: "bg-[#FEF3C7] text-[#B45309] dark:bg-[#3a2f10] dark:text-[#f0c94e]",
    digits: "text-[#D97706] dark:text-[#f0c94e]",
  },
  month: { label: "30 天内", pill: "bg-success-soft text-[#059669] dark:text-success", digits: "text-ink" },
  later: { label: "进行中", pill: "bg-chip text-muted", digits: "text-ink" },
};

function pad(value: number) {
  return String(value).padStart(2, "0");
}

/** 截稿面板 —— 进行中显示实时倒计时；待公布 / 已截止给出明确状态，不伪造时间 */
export function DeadlineCountdown({
  conference,
  now,
}: {
  conference: ConferenceDeadlineDto;
  now: number;
}) {
  const next = conference.status === "open"
    ? upcomingMilestone(conference.edition.milestones, now)
    : null;

  if (next) {
    const nextAt = Date.parse(next.at);
    const urgency = deadlineUrgency(nextAt, now) as Exclude<DeadlineUrgency, "passed">;
    const style = URGENCY_STYLE[urgency];
    const left = remainingUntil(nextAt, now);
    const values = [left.days, left.hours, left.minutes, left.seconds];

    return (
      <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-panel px-5 py-4">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="inline-flex w-fit items-center gap-1.5 rounded-md bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary">
            {milestoneLabel(next)}
            {next.comment && <span className="font-normal text-primary/80">· {next.comment}</span>}
          </span>
          <span className="text-[13px] text-ink-2">{formatInstant(next.at)}</span>
          {next.local && (
            <span className="text-xs text-faint">
              官方时间 {formatOfficialTime(next.local, conference.edition.timezone)}
            </span>
          )}
        </div>

        <div
          className="flex items-start gap-4"
          role="timer"
          aria-label={`距${milestoneLabel(next)}还有 ${left.days} 天 ${left.hours} 小时 ${left.minutes} 分钟`}
        >
          {values.map((value, i) => (
            <div key={UNITS[i]} className="flex items-start gap-4">
              <div className="flex w-11 flex-col items-center gap-0.5">
                <span className={cn("text-[28px] font-bold leading-none tabular-nums", style.digits)}>
                  {pad(value)}
                </span>
                <span className="text-[11px] text-faint">{UNITS[i]}</span>
              </div>
              {i < 3 && (
                <span className={cn("-mx-2 text-xl font-bold leading-[28px]", style.digits)} aria-hidden>
                  :
                </span>
              )}
            </div>
          ))}
        </div>

        <span className={cn("rounded-full px-3 py-1 text-xs font-medium", style.pill)}>
          {style.label}
        </span>
      </div>
    );
  }

  // `open` with no upcoming milestone left means it closed while the page stayed open.
  const tbd = conference.status === "tbd";
  const lastAt = conference.edition.milestones.reduce<string | null>(
    (latest, milestone) =>
      milestone.at && (!latest || Date.parse(milestone.at) > Date.parse(latest)) ? milestone.at : latest,
    null,
  );

  return (
    <div className="mt-4 flex items-center justify-between gap-4 rounded-xl bg-panel px-5 py-4">
      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink-2">
          {tbd ? "截稿时间待公布" : "本届投稿已截止"}
        </span>
        <span className="text-[13px] text-muted">
          {tbd
            ? "组织方尚未公布具体日期，请关注会议官网"
            : `${lastAt ? `最后截止于 ${formatInstant(lastAt)}，` : ""}下一届时间公布后更新`}
        </span>
      </div>
      <span className="rounded-full bg-chip px-3 py-1 text-xs font-medium text-muted">
        {tbd ? "待公布" : "已截止"}
      </span>
    </div>
  );
}

/** 进行中的会议每秒走动：只有倒计时这一小块订阅秒级时钟，卡片本身不随之重渲染 */
export function LiveDeadlineCountdown({ conference }: { conference: ConferenceDeadlineDto }) {
  const now = useNow(1000);
  return <DeadlineCountdown conference={conference} now={now} />;
}
