"use client";

import type { ConferenceTimelinePoint } from "@/clients/backend/conferences";
import { useNow } from "@/features/submit/hooks/use-now";
import {
  deadlineUrgency,
  formatInstant,
  formatOfficialTime,
  milestoneLabel,
  remainingUntil,
  upcomingMilestone,
} from "@/features/submit/lib/deadline-time";
import { cn } from "@/lib/utils";

const UNITS = ["天", "小时", "分", "秒"] as const;

export function DeadlineCountdown({
  points,
  preview,
  timezone,
  fallback,
}: {
  points: readonly ConferenceTimelinePoint[];
  preview: ConferenceTimelinePoint | null;
  timezone: string;
  fallback: string;
}) {
  // Keep the shared seconds clock local to the readout.
  const now = useNow(1000);
  const target = preview ?? upcomingMilestone(points, now);
  if (!target?.at) return <p className="text-sm font-medium text-muted sm:col-start-2 sm:row-start-1 sm:row-span-2 sm:text-right">{fallback}</p>;

  const at = Date.parse(target.at);
  const urgency = deadlineUrgency(at, now);
  const { days, hours, minutes, seconds } = remainingUntil(at, now);
  const derived = "is_derived" in target && target.is_derived;
  const label = milestoneLabel(target);

  return (
    <>
      {target.comment && (
        <p className="min-w-0 wrap-break-word px-1 text-xs leading-relaxed text-muted sm:col-start-1 sm:row-start-2 sm:self-start">
          <span className="mr-1 font-medium text-ink-2">备注</span>
          {target.comment}
        </p>
      )}
      <div className="min-w-0 space-y-1 sm:col-start-2 sm:row-start-1 sm:row-span-2 sm:text-right">
        <p className="text-xs leading-relaxed text-ink-2">
          <span className="font-medium text-primary">{label}{derived ? "（推算）" : ""}</span>
          {" · "}{formatInstant(target.at)}
        </p>
        {target.local && (
          <p className="text-xs leading-relaxed text-muted">
            {derived ? "推算时间" : "官方时间"} {formatOfficialTime(target.local, timezone)}
          </p>
        )}
        {urgency === "passed" ? (
          <p className="text-sm font-semibold text-muted">已过该时间点</p>
        ) : (
          <div
            role="timer"
            aria-label={`距${label}还有 ${days} 天 ${hours} 小时 ${minutes} 分钟 ${seconds} 秒`}
            className={cn(
              "flex flex-wrap items-baseline gap-x-2 text-[22px] font-bold leading-none tabular-nums sm:justify-end",
              urgency === "day" ? "text-danger" : urgency === "week" ? "text-[#B45309] dark:text-[#f0c94e]" : "text-ink",
            )}
          >
            {[days, hours, minutes, seconds].map((value, index) => (
              <span aria-hidden key={UNITS[index]} className="whitespace-nowrap">
                {String(value).padStart(2, "0")} <span className="text-[11px] font-normal text-muted">{UNITS[index]}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
