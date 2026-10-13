"use client";

import { motion } from "framer-motion";
import { Award, Bookmark, BookmarkCheck, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUserPreferences } from "@/stores/user-preferences";
import type { Institution } from "@/types";

const TYPE_TONES: Record<Institution["type"], string> = {
  高校: "bg-primary-soft text-primary",
  研究院: "bg-success-soft text-[#059669] dark:text-success",
  企业实验室: "bg-[#FEF3C7] text-[#B45309] dark:bg-[#3a2f10] dark:text-[#f0c94e]",
};

/** 机构卡片 —— 学者卡片的放大版:单列、4 项统计、完整简介,卡片即详情 */
export function InstitutionCard({
  institution,
  index,
}: {
  institution: Institution;
  index: number;
}) {
  const { bookmarkedInstitutions, toggleInstitutionBookmark } =
    useUserPreferences();
  const bookmarked =
    bookmarkedInstitutions[institution.id] ?? institution.bookmarked ?? false;

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06 }}
      className="rounded-2xl bg-popover p-8 shadow-card transition-shadow hover:shadow-pop"
    >
      <div className="flex gap-6">
        <span
          className="flex size-20 shrink-0 items-center justify-center rounded-2xl text-xl font-bold text-white"
          style={{ backgroundColor: institution.logoColor }}
        >
          {institution.initials}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-bold text-ink">{institution.nameCn}</h3>
              <p className="mt-0.5 text-sm text-muted">{institution.nameEn}</p>
            </div>
            <Button
              variant={bookmarked ? "soft" : "outline"}
              size="sm"
              aria-pressed={bookmarked}
              onClick={() =>
                toggleInstitutionBookmark(institution.id, institution.bookmarked)
              }
              className="rounded-full px-3.5"
            >
              {bookmarked ? (
                <>
                  <BookmarkCheck className="size-3.5" />
                  已收藏
                </>
              ) : (
                <>
                  <Bookmark className="size-3.5" />
                  收藏
                </>
              )}
            </Button>
          </div>

          <p className="mt-2.5 flex items-center gap-2 text-xs text-muted">
            <span
              className={`rounded-md px-2 py-0.5 font-medium ${TYPE_TONES[institution.type]}`}
            >
              {institution.type}
            </span>
            <MapPin className="size-3.5" />
            {institution.location}
          </p>

          <p className="mt-4 text-[14px] leading-relaxed text-muted">
            {institution.intro}
          </p>

          <div className="mt-5 grid grid-cols-4 gap-4 rounded-xl bg-panel px-5 py-4">
            {institution.stats.map((stat) => (
              <div key={stat.label}>
                <p className="text-lg font-bold text-ink">{stat.value}</p>
                <p className="mt-0.5 text-xs text-faint">{stat.label}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {institution.fields.map((field) => (
              <span
                key={field}
                className="rounded-md bg-chip px-2 py-1 text-xs text-muted"
              >
                {field}
              </span>
            ))}
          </div>

          <p className="mt-3 flex items-start gap-2 text-[13px] text-muted">
            <Award className="mt-0.5 size-4 shrink-0 text-primary" />
            {institution.highlight}
          </p>
        </div>
      </div>
    </motion.article>
  );
}
