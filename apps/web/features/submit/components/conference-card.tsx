"use client";

import { memo, type Ref } from "react";
import { motion } from "framer-motion";
import { Calendar, ExternalLink, Folder, MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ConferenceDeadlineDto } from "@/clients/backend/conferences";
import { AddToCalendarMenu } from "./add-to-calendar-menu";
import { ConferenceFollowButton } from "./conference-follow-button";
import { DeadlineCountdown } from "./deadline-countdown";
import {
  compactTimeline,
  deadlineUrgency,
  formatInstant,
  milestoneLabel,
  upcomingMilestone,
} from "@/features/submit/lib/deadline-time";

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

/**
 * 会议截稿卡片 —— 沿用投稿页卡片视觉，数据来自 FastAPI 会议截稿快照。
 * memo：只有进行中的会议会收到走动的 `now`，其余卡片不随每秒时钟重渲染。
 */
export const ConferenceCard = memo(function ConferenceCard({
  ref,
  conference,
  categoryName,
  now,
  index,
  following,
  followResolving,
  highlighted,
}: {
  ref?: Ref<HTMLElement>;
  conference: ConferenceDeadlineDto;
  categoryName: string | undefined;
  now: number;
  index: number;
  following: boolean;
  followResolving: boolean;
  /** 从关注区或日历链接跳转过来时短暂高亮 */
  highlighted: boolean;
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
      ref={ref}
      // 筛选变化时：留下的卡片平移到新位置，移除的淡出，新出现的淡入
      layout="position"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.18 } }}
      transition={{
        duration: 0.3,
        delay: Math.min(index, 8) * 0.04,
        layout: { type: "spring", stiffness: 420, damping: 38 },
      }}
      // 日历菜单展开时浮在后续卡片之上
      id={`conference-${conference.id}`}
      className={cn(
        "relative scroll-mt-32 rounded-2xl bg-card shadow-card ring-2 ring-transparent transition-[box-shadow] duration-500 has-[[data-open]]:z-10",
        highlighted && "ring-primary/50",
      )}
    >
      <span className={cn("absolute inset-y-0 left-0 w-1 rounded-l-2xl", accentClass(conference, now))} />

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

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <ConferenceFollowButton conference={conference} following={following} resolving={followResolving} />
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
          {next && <AddToCalendarMenu conference={conference} next={next} now={now} />}
        </div>
      </div>
    </motion.article>
  );
});
