"use client";

import type { Ref } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BellRing } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConferenceDeadlineDto } from "@/clients/backend/conferences";
import {
  deadlineUrgency,
  formatRemainingShort,
  milestoneLabel,
  upcomingMilestone,
  type DeadlineUrgency,
} from "@/features/submit/lib/deadline-time";

const URGENCY_TEXT: Record<Exclude<DeadlineUrgency, "passed">, string> = {
  day: "text-danger",
  week: "text-[#D97706] dark:text-[#f0c94e]",
  month: "text-ink",
  later: "text-ink",
};

const URGENCY_BAR: Record<Exclude<DeadlineUrgency, "passed">, string> = {
  day: "bg-danger",
  week: "bg-[#F59E0B]",
  month: "bg-success",
  later: "bg-success",
};

function FollowedTile({
  ref,
  conference,
  now,
  onSelect,
}: {
  ref?: Ref<HTMLLIElement>;
  conference: ConferenceDeadlineDto;
  now: number;
  onSelect: (conference: ConferenceDeadlineDto) => void;
}) {
  const next = conference.status === "open" ? upcomingMilestone(conference.edition.milestones, now) : null;
  const urgency = next ? (deadlineUrgency(Date.parse(next.at), now) as Exclude<DeadlineUrgency, "passed">) : null;

  return (
    <motion.li
      ref={ref}
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
      className="shrink-0 snap-start"
    >
      <button
        type="button"
        onClick={() => onSelect(conference)}
        className="relative flex h-full w-[200px] cursor-pointer flex-col gap-1 overflow-hidden rounded-xl border border-line bg-panel px-3.5 py-2.5 text-left transition-colors hover:border-primary/40"
      >
        <span className={cn("absolute inset-y-0 left-0 w-0.5", urgency ? URGENCY_BAR[urgency] : "bg-line")} />
        <span className="truncate text-sm font-semibold text-ink">
          {conference.title} <span className="font-medium text-muted">{conference.edition.year}</span>
        </span>
        {next && urgency ? (
          <span className="flex items-baseline justify-between gap-2 text-xs">
            <span className="text-muted">{milestoneLabel(next)}</span>
            <span className={cn("font-semibold tabular-nums", URGENCY_TEXT[urgency])}>
              {formatRemainingShort(Date.parse(next.at), now)}
            </span>
          </span>
        ) : (
          <span className="text-xs text-faint">{conference.status === "tbd" ? "截稿时间待公布" : "本届已截止"}</span>
        )}
      </button>
    </motion.li>
  );
}

/** 投稿页置顶的关注区 —— 一眼看到关注会议的剩余时间，点击定位到对应卡片 */
export function FollowedConferences({
  items,
  now,
  onSelect,
}: {
  items: ConferenceDeadlineDto[];
  now: number;
  onSelect: (conference: ConferenceDeadlineDto) => void;
}) {
  return (
    <AnimatePresence initial={false}>
      {items.length > 0 && (
        <motion.section
          key="followed"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="overflow-hidden"
          aria-label="我关注的会议"
        >
          <div className="rounded-2xl bg-card p-4 shadow-card">
            <div className="flex items-center gap-2">
              <BellRing className="size-4 text-primary" />
              <h2 className="text-[15px] font-semibold text-ink">我关注的会议</h2>
              <span className="text-sm text-faint">{items.length}</span>
              <span className="ml-auto hidden text-xs text-faint sm:inline">7 天内截止会在侧边栏「投稿」提醒</span>
            </div>
            <ul className="-mx-1 mt-3 flex snap-x gap-2.5 overflow-x-auto px-1 pb-1">
              <AnimatePresence initial={false} mode="popLayout">
                {items.map((conference) => (
                  <FollowedTile key={conference.id} conference={conference} now={now} onSelect={onSelect} />
                ))}
              </AnimatePresence>
            </ul>
          </div>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
