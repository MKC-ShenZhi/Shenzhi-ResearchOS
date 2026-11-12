"use client";

import { Fragment, useState } from "react";
import type { ConferenceTimelinePoint } from "@/clients/backend/conferences";
import { formatInstant, formatTimelineDate, milestoneLabel } from "@/features/submit/lib/deadline-time";
import { cn } from "@/lib/utils";
import { DeadlineCountdown } from "./deadline-countdown";

const POINT_COLOR: Record<ConferenceTimelinePoint["kind"], string> = {
  abstract: "text-sky-600 dark:text-sky-400",
  full: "text-primary",
  rebuttal: "text-amber-600 dark:text-amber-400",
  decision: "text-emerald-600 dark:text-emerald-400",
  opening: "text-violet-600 dark:text-violet-400",
};

export function ConferenceTimeline({
  points,
  now,
  timezone,
  fallback,
  label,
}: {
  points: readonly ConferenceTimelinePoint[];
  now: number;
  timezone: string;
  fallback: string;
  label: string;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [focused, setFocused] = useState<number | null>(null);
  const activeIndex = hovered ?? focused;
  const dated = points.flatMap((point, index) => point.at ? [{ point, index, at: Date.parse(point.at) }] : []);
  const next = dated.find((entry) => entry.at > now);
  // Keep the compact axis useful for rolling deadlines; the expanded list retains all past rounds.
  const mostRecent = dated.findLast((entry) => entry.at <= now);
  const visible = dated.filter((entry) => entry.at > now || entry === mostRecent);
  const stops = [...visible, { point: null, index: -1, at: now }].sort((a, b) => a.at - b.at);
  const duration = stops[stops.length - 1].at - stops[0].at || 1;

  return (
    <div className="mt-3 grid min-w-0 items-center gap-2 sm:grid-cols-2 sm:grid-rows-[auto_1fr] sm:gap-x-5 sm:gap-y-0">
      {dated.length ? (
        <div className="min-w-0 overflow-x-auto px-1 sm:mt-2 sm:self-start" aria-label={label} role="group">
          <div className="relative flex w-full items-start py-1" style={{ minWidth: `${stops.length * 2.625}rem` }}>
            <span aria-hidden className="pointer-events-none absolute inset-x-[1.25rem] top-4 h-0.5 rounded-full bg-primary/30" />
            {stops.map(({ point, index, at }, i) => (
              <Fragment key={index}>
                {i > 0 && <span aria-hidden style={{ flexGrow: (at - stops[i - 1].at) / duration }} />}
                {point?.at ? (
                  <button
                    type="button"
                    onPointerEnter={(event) => { if (event.pointerType !== "touch") setHovered(index); }}
                    onPointerLeave={() => setHovered(null)}
                    onFocus={(event) => { if (event.currentTarget.matches(":focus-visible")) setFocused(index); }}
                    onBlur={() => setFocused(null)}
                    onPointerUp={(event) => {
                      if (event.pointerType === "touch") {
                        event.currentTarget.focus();
                        setFocused(index);
                      }
                    }}
                    aria-label={`${milestoneLabel(point)}${point.comment ? ` · ${point.comment}` : ""} · ${formatInstant(point.at)}${"is_derived" in point && point.is_derived ? "（推算）" : ""}`}
                    className={cn("relative flex w-[2.625rem] shrink-0 cursor-pointer flex-col items-center rounded-md py-1 text-xs focus-visible:outline-2 focus-visible:outline-primary", at <= now ? "text-faint" : POINT_COLOR[point.kind])}
                  >
                    <span className="flex h-4 items-center">
                      <span className={cn("size-2.5 rounded-full border-2 border-current bg-card", (activeIndex === index || (activeIndex === null && next?.index === index)) && "bg-current ring-2 ring-current/20")} />
                    </span>
                    <span className="whitespace-nowrap text-[10px] tabular-nums">{formatTimelineDate(point.at)}</span>
                  </button>
                ) : (
                  <span aria-label="现在" className="relative flex w-[2.625rem] shrink-0 flex-col items-center py-1 text-amber-600 dark:text-amber-400">
                    <span className="flex h-4 items-center"><span className="size-2.5 rounded-full bg-current ring-2 ring-current/20" /></span>
                    <span className="text-[10px]">现在</span>
                  </span>
                )}
              </Fragment>
            ))}
          </div>
        </div>
      ) : <p className="text-xs text-faint sm:row-span-2">暂无已公布的时间点</p>}
      {next || activeIndex !== null ? (
        <DeadlineCountdown points={points} preview={activeIndex === null ? null : points[activeIndex] ?? null} timezone={timezone} fallback={fallback} />
      ) : <p className="text-sm font-medium text-muted sm:col-start-2 sm:row-start-1 sm:row-span-2 sm:text-right">{fallback}</p>}
    </div>
  );
}
