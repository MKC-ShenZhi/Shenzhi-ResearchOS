import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { scholarHref } from "@/lib/navigation/scholar";
import type { ScholarProfile } from "../types";
import { scholarName } from "../presentation";
import { Affiliations, ScholarAvatar, ScholarMetrics } from "./profile-parts";

export function ScholarCard({
  scholar,
  returnTo,
}: {
  scholar: ScholarProfile;
  returnTo: string;
}) {
  return (
    <Link
      href={scholarHref(scholar.scholar_id, returnTo)}
      className="group flex min-w-0 flex-col rounded-2xl border border-line bg-card p-5 transition-[border-color,box-shadow] hover:border-primary/35 hover:shadow-card focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary sm:p-6"
    >
      <div className="flex items-start gap-4">
        <ScholarAvatar scholar={scholar} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h2 className="break-words text-lg font-semibold tracking-tight text-ink transition-colors group-hover:text-primary">
              {scholarName(scholar)}
            </h2>
            <ArrowUpRight
              aria-hidden="true"
              className="mt-1 size-4 shrink-0 text-faint transition-colors group-hover:text-primary"
            />
          </div>
          {scholar.name_zh?.trim() && scholar.name_en?.trim() ? (
            <p className="mt-0.5 break-words text-sm text-muted">
              {scholar.name_en}
            </p>
          ) : null}
          <div className="mt-3">
            <Affiliations scholar={scholar} compact />
          </div>
        </div>
      </div>
      <p className="mt-5 line-clamp-3 min-h-[4.5rem] break-words text-sm leading-6 text-ink-2">
        {scholar.bio_zh?.trim() ||
          scholar.bio_en?.trim() ||
          "个人简介暂无数据。"}
      </p>
      <div className="mt-auto pt-5">
        <div className="border-t border-line pt-4">
          <ScholarMetrics scholar={scholar} compact />
        </div>
      </div>
    </Link>
  );
}
