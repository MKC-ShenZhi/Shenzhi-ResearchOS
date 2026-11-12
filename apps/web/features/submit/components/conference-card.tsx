"use client";

import { memo, type Ref } from "react";
import { motion } from "framer-motion";
import { Calendar, ChevronDown, ExternalLink, Folder, MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ConferenceDeadlineDto } from "@/clients/backend/conferences";
import { AddToCalendarMenu } from "./add-to-calendar-menu";
import { ConferenceFollowButton } from "./conference-follow-button";
import { ConferenceTimeline } from "./conference-timeline";
import {
  deadlineUrgency,
  formatInstant,
  formatOfficialTime,
  milestoneLabel,
  timelinePoints,
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
 * 秒级时钟仅由倒计时订阅，卡片及时间轴按分钟更新。
 */
export const ConferenceCard = memo(function ConferenceCard({
  ref,
  conference,
  categoryName,
  now,
  index,
  animateLayout,
  following,
  followResolving,
  highlighted,
  expanded,
  onToggleDetails,
}: {
  ref?: Ref<HTMLElement>;
  conference: ConferenceDeadlineDto;
  categoryName: string | undefined;
  now: number;
  index: number;
  /** 只有首批卡片参与布局补位动画；后续批次在视口外，跳过布局追踪以降低追加成本 */
  animateLayout: boolean;
  following: boolean;
  followResolving: boolean;
  /** 从关注区或日历链接跳转过来时短暂高亮 */
  highlighted: boolean;
  expanded: boolean;
  onToggleDetails: (id: string) => void;
}) {
  const { edition, rank } = conference;
  const next = conference.source_removed ? null : upcomingMilestone(edition.milestones, now);
  const points = timelinePoints(edition);
  const subdued = conference.status === "closed" && !expanded && !upcomingMilestone(points, now);
  const hasDetails = !conference.source_removed && points.length > 0;
  const detailsId = `conference-details-${conference.id}`;
  const toggleDetails = () => onToggleDetails(conference.id);
  const meta = [
    { icon: Folder, text: categoryName ?? conference.category },
    { icon: MapPin, text: edition.place },
    { icon: Calendar, text: edition.date },
  ].filter((item): item is { icon: typeof Folder; text: string } => Boolean(item.text));

  return (
    <motion.article
      ref={ref}
      // 筛选变化时：留下的卡片平移到新位置，移除的淡出，新出现的淡入
      layout={animateLayout ? "position" : false}
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
      onClick={hasDetails ? (event) => {
        const target = event.target;
        if (!(target instanceof Element) || !event.currentTarget.contains(target)) return;
        if (!target.closest("a, button, input, select, textarea, label, [role=button], [role=menuitem]")) toggleDetails();
      } : undefined}
      className={cn(
        "relative scroll-mt-32 rounded-2xl ring-2 ring-transparent transition-[background-color,box-shadow] duration-300 motion-reduce:transition-none has-[[data-open]]:z-10",
        subdued ? "bg-card/25 shadow-none" : "bg-card shadow-card",
        highlighted && "ring-primary/50",
        hasDetails && "cursor-pointer",
      )}
    >
      <span className={cn("absolute inset-y-0 left-0 w-1 rounded-l-2xl", accentClass(conference, now))} />

      <div className={cn("p-4 pl-5 transition-opacity duration-300 motion-reduce:transition-none sm:px-5 sm:pl-6", subdued && "opacity-60")}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3 className="text-xl font-bold leading-tight text-ink">
            {conference.title} <span className="font-semibold text-muted">{edition.year}</span>
          </h3>
          <div className="flex flex-wrap justify-end gap-2">
            {rank.ccf && <Badge variant="plain">CCF {rank.ccf}</Badge>}
            {rank.core && <Badge variant="plain">CORE {rank.core}</Badge>}
            {rank.thcpl && <Badge variant="plain">TH-CPL {rank.thcpl}</Badge>}
            {!rank.ccf && <Badge variant="plain">非 CCF</Badge>}
          </div>
        </div>

        <p className="mt-1.5 text-sm text-muted">{conference.description}</p>

        {meta.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            {meta.map(({ icon: Icon, text }) => (
              <span key={text} className="flex items-center gap-1.5 text-[13px] text-muted">
                <Icon className="size-3.5 shrink-0 text-faint" />
                {text}
              </span>
            ))}
          </div>
        )}

        {conference.source_removed ? (
          <div className="mt-4 rounded-xl border border-line px-5 py-4 text-sm text-muted">
            <p className="font-medium text-ink-2">暂无最新会议数据</p>
            <p className="mt-1 leading-relaxed">目前保留最后一次资料，截稿信息请以会议官网为准。</p>
          </div>
        ) : conference.needs_update ? (
          <p className="mt-4 text-sm text-muted">
            待更新 · 暂无新一届截稿信息，{" "}
            <a href="https://github.com/ccfddl/ccf-deadlines" target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">查看数据来源</a>
          </p>
        ) : (
          <ConferenceTimeline
            points={points}
            now={now}
            timezone={edition.timezone}
            fallback={conference.status === "tbd" ? "截稿时间待公布" : "暂无后续时间点"}
            label={`${conference.title} ${edition.year} 时间轴`}
          />
        )}

        {hasDetails && (
          <div id={detailsId} hidden={!expanded} className="mt-3 space-y-3 border-t border-line pt-2">
            {expanded && (
              <>
                <ol className="divide-y divide-line" aria-label={`${conference.title} ${edition.year} 时间线详情`}>
                  {points.map((point, index) => {
                    const derived = "is_derived" in point && point.is_derived;
                    return (
                      <li
                        key={index}
                        className={cn("flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-1.5 text-xs", point.at && Date.parse(point.at) <= now ? "text-faint" : "text-muted")}
                      >
                        <span>
                          <span className="font-medium">{milestoneLabel(point)}{derived ? "（推算）" : ""}</span>
                          {point.comment && <> · {point.comment}</>}
                        </span>
                        <span className="tabular-nums">
                          {point.at ? formatInstant(point.at) : "待公布"}
                          {point.local && <span className="ml-2 text-faint">{formatOfficialTime(point.local, edition.timezone)}</span>}
                        </span>
                      </li>
                    );
                  })}
                </ol>
                {Boolean(conference.accept_rates?.length) && (
                  <div className="border-t border-line pt-3">
                    <h4 className="mb-2 text-sm font-medium text-ink-2">历史录用率</h4>
                    <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,14rem),1fr))] gap-2.5">
                      {conference.accept_rates?.map((rate, index) => {
                        const showCounts = rate.rate !== null || !rate.str;
                        return (
                          <li key={index} className="flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-panel px-3 py-2.5">
                            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                              <span className="text-xs font-medium text-muted">{rate.year} 年</span>
                              {rate.rate !== null ? (
                                <span className="text-base font-semibold leading-tight text-ink tabular-nums">
                                  {(rate.rate * 100).toFixed(1)}%
                                </span>
                              ) : (
                                <span className="min-w-0 wrap-break-word text-xs text-muted">{rate.str ?? "录用率未提供"}</span>
                              )}
                            </div>
                            <div className="mt-auto flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-muted tabular-nums">
                              {showCounts && rate.accepted !== null && <span>录用 {rate.accepted}</span>}
                              {showCounts && rate.submitted !== null && <span>投稿 {rate.submitted}</span>}
                              {rate.source && (
                                <a
                                  className="ml-auto inline-flex items-center gap-1 text-primary hover:underline underline-offset-2"
                                  href={rate.source}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  aria-label={`${rate.year} 年录用统计来源`}
                                >
                                  来源 <ExternalLink aria-hidden className="size-3" />
                                </a>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
          {hasDetails && (
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={detailsId}
              onClick={toggleDetails}
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "mr-auto px-1 text-muted")}
            >
              <ChevronDown className={cn("transition-transform", expanded && "rotate-180")} />
              {expanded ? "收起详情" : "展开详情"}
            </button>
          )}
          {next && <AddToCalendarMenu conference={conference} next={next} now={now} />}
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
          <ConferenceFollowButton conference={conference} following={following} resolving={followResolving} />
        </div>
      </div>
    </motion.article>
  );
});
