"use client";

import { motion } from "framer-motion";
import {
  BookOpen,
  Calendar,
  Folder,
  MapPin,
  Quote,
  TrendingUp,
} from "lucide-react";
import { VenueBadge } from "./venue-badge";
import { cn } from "@/lib/utils";
import type { Venue, VenueMetaIcon } from "@/types";

const META_ICONS: Record<VenueMetaIcon, typeof Folder> = {
  folder: Folder,
  pin: MapPin,
  cal: Calendar,
  chart: TrendingUp,
  quote: Quote,
};

/** 会议/期刊卡片 —— 对应投稿详情页 SVG 的卡片 */
export function VenueCard({ venue, index }: { venue: Venue; index: number }) {
  const isConference = venue.kind === "conference";

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06 }}
      className="relative overflow-hidden rounded-2xl bg-card shadow-card"
    >
      {/* 左侧状态色条 */}
      <span
        className={cn(
          "absolute inset-y-0 left-0 w-1",
          venue.accent === "danger" ? "bg-danger" : "bg-success",
        )}
      />

      <div className="p-6 pl-7">
        {/* 标题 + 徽章 */}
        <div className="flex items-start justify-between gap-4">
          <h3 className="flex items-center gap-2 text-[22px] font-bold leading-tight text-ink">
            {venue.abbr}
            {!isConference && (
              <BookOpen className="size-5 text-muted" strokeWidth={1.8} />
            )}
          </h3>
          <div className="flex max-w-[60%] flex-wrap justify-end gap-2">
            {venue.badges.map((badge) => (
              <VenueBadge key={badge} name={badge} />
            ))}
          </div>
        </div>

        <p className="mt-1.5 text-sm text-muted">{venue.fullName}</p>

        {/* 元信息行 */}
        <div className="mt-3 space-y-2">
          {venue.metaRows.map((row, ri) => (
            <div key={ri} className="flex flex-wrap items-center gap-x-6 gap-y-1.5">
              {row.map(([icon, text]) => {
                const Icon = META_ICONS[icon];
                return (
                  <span
                    key={text}
                    className="flex items-center gap-1.5 text-[13px] text-muted"
                  >
                    <Icon className="size-3.5 shrink-0 text-faint" />
                    {text}
                  </span>
                );
              })}
            </div>
          ))}
        </div>

        {/* 研究方向 chips */}
        {venue.chips.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2.5">
            {venue.chips.map((chip) => (
              <span
                key={chip}
                className="flex h-7 items-center rounded-lg bg-chip px-3 text-xs text-muted"
              >
                {chip}
              </span>
            ))}
          </div>
        )}

      </div>
    </motion.article>
  );
}
