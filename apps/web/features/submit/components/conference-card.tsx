"use client";

import { memo } from "react";
import { motion } from "framer-motion";
import { Calendar, CalendarPlus, ExternalLink, Folder, MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ConferenceDeadlineDto } from "@/clients/backend/conferences";
import { DeadlineCountdown } from "./deadline-countdown";
import {
  compactTimeline,
  deadlineUrgency,
  formatInstant,
  milestoneLabel,
  upcomingMilestone,
} from "@/features/submit/lib/deadline-time";
import { buildConferenceIcs } from "@/features/submit/lib/ics";

function accentClass(conference: ConferenceDeadlineDto, now: number): string {
  const next = conference.status === "open"
    ? upcomingMilestone(conference.edition.milestones, now)
    : null;
  if (!next) return conference.status === "tbd" ? "bg-primary/60" : "bg-line";
  const urgency = deadlineUrgency(Date.parse(next.at), now);
  if (urgency === "day") return "bg-danger";
  if (urgency === "week") return "bg-[#F59E0B]";
  return "bg-success";
}

function downloadIcs(conference: ConferenceDeadlineDto) {
  const ics = buildConferenceIcs(conference, new Date());
  if (!ics) return;
  const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${conference.title.replace(/[^\w.-]+/g, "_")}-${conference.edition.year}.ics`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * 会议截稿卡片 —— 沿用投稿页卡片视觉，数据来自 FastAPI 会议截稿快照。
 * memo：只有进行中的会议会收到走动的 `now`，其余卡片不随每秒时钟重渲染。
 */
export const ConferenceCard = memo(function ConferenceCard({
  conference,
  categoryName,
  now,
  index,
}: {
  conference: ConferenceDeadlineDto;
  categoryName: string | undefined;
  now: number;
  index: number;
}) {
  const { edition, rank } = conference;
  const closed = conference.status === "closed";
  const next = upcomingMilestone(edition.milestones, now);
  const timeline = compactTimeline(edition.milestones, now);
  const meta = [
    { icon: Folder, text: categoryName ?? conference.category },
    { icon: MapPin, text: edition.place },
    { icon: Calendar, text: edition.date },
  ].filter((item): item is { icon: typeof Folder; text: string } => Boolean(item.text));

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index, 8) * 0.04 }}
      className="relative overflow-hidden rounded-2xl bg-card shadow-card"
    >
      <span className={cn("absolute inset-y-0 left-0 w-1", accentClass(conference, now))} />

      <div className={cn("p-6 pl-7", closed && "opacity-75")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h3 className="text-[22px] font-bold leading-tight text-ink">
            {conference.title} <span className="font-semibold text-muted">{edition.year}</span>
          </h3>
          <div className="flex flex-wrap justify-end gap-2">
            {rank.ccf && <Badge variant="green">CCF {rank.ccf}</Badge>}
            {rank.core && <Badge variant="violet">CORE {rank.core}</Badge>}
            {rank.thcpl && <Badge variant="amber">TH-CPL {rank.thcpl}</Badge>}
            {!rank.ccf && <Badge variant="gray">非 CCF</Badge>}
          </div>
        </div>

        <p className="mt-1.5 text-sm text-muted">{conference.description}</p>

        {meta.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1.5">
            {meta.map(({ icon: Icon, text }) => (
              <span key={text} className="flex items-center gap-1.5 text-[13px] text-muted">
                <Icon className="size-3.5 shrink-0 text-faint" />
                {text}
              </span>
            ))}
          </div>
        )}

        <DeadlineCountdown conference={conference} now={now} />

        {edition.milestones.length > 1 && (
          <ol className="mt-3 flex flex-wrap gap-2" aria-label={`${conference.title} ${edition.year} 时间线`}>
            {timeline.passedCount > 0 && (
              <li className="flex h-7 items-center rounded-lg bg-chip px-2.5 text-xs text-faint">
                已截止 {timeline.passedCount} 轮
              </li>
            )}
            {timeline.visible.map((milestone) => (
              <li
                key={edition.milestones.indexOf(milestone)}
                className={cn(
                  "flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-xs",
                  milestone === next ? "bg-primary-soft text-primary" : "bg-chip text-muted",
                )}
              >
                <span className="font-medium">{milestoneLabel(milestone)}</span>
                {milestone.comment && <span>{milestone.comment}</span>}
                <span>{milestone.at ? formatInstant(milestone.at) : "待公布"}</span>
              </li>
            ))}
            {timeline.hiddenUpcomingCount > 0 && (
              <li className="flex h-7 items-center rounded-lg bg-chip px-2.5 text-xs text-faint">
                另有 {timeline.hiddenUpcomingCount} 轮
              </li>
            )}
          </ol>
        )}

        {(edition.link || next) && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {edition.link && (
              <a
                href={edition.link}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <ExternalLink />
                会议官网
              </a>
            )}
            {next && (
              <Button variant="soft" size="sm" onClick={() => downloadIcs(conference)}>
                <CalendarPlus />
                加入日历
              </Button>
            )}
          </div>
        )}
      </div>
    </motion.article>
  );
});
