"use client";

import { deadlineUrgency, upcomingMilestone } from "@/features/submit/lib/deadline-time";
import { useFollowedConferences } from "@/features/submit/hooks/use-conference-follows";
import { useNow } from "@/features/submit/hooks/use-now";

/**
 * 侧边栏「投稿」上的截稿提醒：关注的会议中 7 天内截止的数量。
 * 用户在站内任意页面都能看到，点进投稿页查看倒计时。
 */
export function FollowedDeadlineBadge({ compact = false }: { compact?: boolean }) {
  const { items } = useFollowedConferences();
  const now = useNow(60_000);
  const dueSoon = items.filter((conference) => {
    if (conference.status !== "open") return false;
    const next = upcomingMilestone(conference.edition.milestones, now);
    if (!next) return false;
    const urgency = deadlineUrgency(Date.parse(next.at), now);
    return urgency === "day" || urgency === "week";
  }).length;
  if (dueSoon === 0) return null;

  const label = `${dueSoon} 个关注的会议 7 天内截止`;
  if (compact) {
    return (
      <span
        aria-label={label}
        title={label}
        className="absolute right-1.5 top-1.5 size-2 rounded-full bg-danger ring-2 ring-sidebar"
      />
    );
  }
  return (
    <span
      aria-label={label}
      title={label}
      className="flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-danger px-1 text-[11px] font-semibold leading-none text-white"
    >
      {dueSoon}
    </span>
  );
}
