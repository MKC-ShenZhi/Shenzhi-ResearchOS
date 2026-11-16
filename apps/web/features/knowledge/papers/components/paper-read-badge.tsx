"use client";

import { cn } from "@/lib/utils";
import { usePaperReadStatus } from "../use-paper-read-status";

export function PaperReadBadge({ status, className }: { status: "read" | "reading"; className?: string }) {
  return (
    <span
      aria-label={status === "read" ? "已读" : "在读"}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-md px-2 py-1 text-xs font-semibold leading-none text-white",
        status === "read" ? "bg-[#0e7490]" : "bg-[#a16207]",
        className,
      )}
    >
      {status === "read" ? "已读" : "在读"}
    </span>
  );
}

export function PaperReadBadgeForPaper({ paperId, className }: { paperId: string; className?: string }) {
  const status = usePaperReadStatus(paperId);
  return status ? <PaperReadBadge status={status} className={className} /> : null;
}
