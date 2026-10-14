"use client";

import { cn } from "@/lib/utils";
import { usePaperReadStatus } from "../use-paper-read-status";

export function PaperReadBadge({ className }: { className?: string }) {
  return (
    <span
      aria-label="已阅读"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-md bg-[#0e7490] px-2 py-1 text-xs font-semibold leading-none text-white",
        className,
      )}
    >
      已阅读
    </span>
  );
}

export function PaperReadBadgeForPaper({ paperId, className }: { paperId: string; className?: string }) {
  const isRead = usePaperReadStatus(paperId);
  return isRead ? <PaperReadBadge className={className} /> : null;
}
