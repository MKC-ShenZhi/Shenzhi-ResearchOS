"use client";

import { useCallback, useRef, useState } from "react";
import { CalendarPlus, ChevronDown, Download, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { usePopoverPlacement } from "@/lib/use-popover-placement";
import type { ConferenceDeadlineDto, ConferenceMilestoneDto } from "@/clients/backend/conferences";
import { formatInstant, milestoneLabel } from "@/features/submit/lib/deadline-time";
import { googleCalendarUrl, outlookCalendarUrl } from "@/features/submit/lib/calendar-links";
import { buildConferenceIcs } from "@/features/submit/lib/ics";
import { useDismiss } from "@/features/submit/hooks/use-dismiss";
import { PopoverPanel } from "./popover-panel";

/** 深知内该会议的定位链接；投稿页读取 `focus` 后滚动并高亮对应卡片 */
export function conferencePageUrl(conferenceId: string): string {
  return `${window.location.origin}/submit?focus=${encodeURIComponent(conferenceId)}`;
}

function downloadIcs(conference: ConferenceDeadlineDto) {
  const ics = buildConferenceIcs(conference, new Date(), conferencePageUrl(conference.id));
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

const itemClass =
  "flex w-full cursor-pointer items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-chip";

/**
 * 导出日历（次要入口，主操作是站内「关注截稿」）—— 网页日历（Google / Outlook）打开预填好的新建事件页，
 * 一次添加下一个截稿节点；.ics 面向 Apple 日历、飞书等本地日历，包含全部未截止节点和提前 1 天提醒。
 * 所有事件都带深知会议页链接，提醒点开后回到站内。
 */
export function AddToCalendarMenu({
  conference,
  next,
  now,
}: {
  conference: ConferenceDeadlineDto;
  next: ConferenceMilestoneDto & { at: string };
  now: number;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const placement = usePopoverPlacement(open, rootRef, 300);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, rootRef, close);

  const upcomingCount = conference.edition.milestones.filter(
    (milestone) => milestone.at && Date.parse(milestone.at) > now,
  ).length;
  // 只在展开后生成链接：需要浏览器的 origin
  const pageUrl = open ? conferencePageUrl(conference.id) : "";
  const webCalendars = open
    ? [
      { label: "Google 日历", href: googleCalendarUrl(conference, next, pageUrl) },
      { label: "Outlook（个人账户）", href: outlookCalendarUrl(conference, next, pageUrl) },
      {
        label: "Outlook（工作 / 学校账户）",
        href: outlookCalendarUrl(conference, next, pageUrl, "outlook.office.com"),
      },
    ]
    : [];

  return (
    <div ref={rootRef} className="relative" data-open={open || undefined}>
      <Button
        variant="ghost"
        size="sm"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="text-muted"
      >
        <CalendarPlus />
        导出日历
        <ChevronDown className={cn("transition-transform", open && "rotate-180")} />
      </Button>

      <PopoverPanel open={open} placement={placement} className="w-72">
        <div role="menu" aria-label="导出日历">
          <p className="px-2.5 pb-1.5 pt-1 text-xs text-faint">
            导出「{milestoneLabel(next)}{next.comment ? ` · ${next.comment}` : ""}」
            <span className="block text-ink-2">{formatInstant(next.at)}</span>
          </p>
          {webCalendars.map((calendar) => (
            <a
              key={calendar.label}
              role="menuitem"
              href={calendar.href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={close}
              className={cn(itemClass, "items-center text-[13px] text-ink-2")}
            >
              <span className="flex-1">{calendar.label}</span>
              <ExternalLink className="size-3.5 text-faint" />
            </a>
          ))}
          <div className="my-1 border-t border-line" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              downloadIcs(conference);
              close();
            }}
            className={itemClass}
          >
            <Download className="mt-0.5 size-3.5 shrink-0 text-faint" />
            <span className="flex flex-col gap-0.5">
              <span className="text-[13px] text-ink-2">Apple 日历 / 飞书 / 其他（.ics）</span>
              <span className="text-xs text-faint">
                {upcomingCount > 1 ? `含全部 ${upcomingCount} 个未截止节点，` : ""}提前 1 天提醒
              </span>
            </span>
          </button>
        </div>
      </PopoverPanel>
    </div>
  );
}
