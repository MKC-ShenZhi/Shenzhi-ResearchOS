"use client";

import Image from "next/image";
import { useState } from "react";
import { AlertCircle, Building2, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  formatScholarMetric,
  scholarInitials,
  scholarName,
} from "../presentation";
import type { ScholarProfile } from "../types";

export function DemoBadge() {
  return (
    <span className="inline-flex w-fit items-center gap-2 rounded-full border border-primary/15 bg-primary-soft px-3 py-1.5 text-[11px] font-medium tracking-wide text-primary">
      <span className="size-1.5 rounded-full bg-primary" />
      Mock Demo · 演示数据
    </span>
  );
}

export function ScholarAvatar({
  scholar,
  large = false,
}: {
  scholar: ScholarProfile;
  large?: boolean;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const src = scholar.avatar_path?.trim();
  const hasImage = src && src !== failedSrc;
  return (
    <span
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-primary/10 bg-primary-soft font-medium tracking-wide text-primary",
        large
          ? "size-24 text-3xl sm:size-28"
          : "size-16 text-xl sm:size-20 sm:text-2xl",
      )}
    >
      {hasImage ? (
        <Image
          src={src}
          alt={`${scholarName(scholar)}的演示头像`}
          fill
          sizes={large ? "112px" : "80px"}
          unoptimized
          className="object-cover"
          onError={() => setFailedSrc(src)}
        />
      ) : (
        <span aria-label={`${scholarName(scholar)}的占位头像`}>
          {scholarInitials(scholar.name_en)}
        </span>
      )}
    </span>
  );
}

export function Affiliations({
  scholar,
  compact = false,
}: {
  scholar: ScholarProfile;
  compact?: boolean;
}) {
  const affiliations = (scholar.affiliations ?? []).filter(
    (item) => item.institution?.trim() || item.position?.trim(),
  );
  if (!affiliations.length)
    return <p className="text-sm text-muted">当前任职暂无数据</p>;
  return (
    <div
      className={cn(
        "space-y-1.5 text-sm leading-relaxed text-muted",
        compact && "text-[13px]",
      )}
    >
      {affiliations.map((item, i) => (
        <p className="flex items-start gap-2" key={`${item.institution}-${i}`}>
          <Building2
            aria-hidden="true"
            className="mt-0.5 size-3.5 shrink-0 text-faint"
          />
          <span className="min-w-0 break-words">
            {[item.position, item.institution].filter(Boolean).join(" · ")}
          </span>
        </p>
      ))}
    </div>
  );
}

export function ScholarMetrics({
  scholar,
  compact = false,
}: {
  scholar: ScholarProfile;
  compact?: boolean;
}) {
  return (
    <dl
      className={cn(
        "grid grid-cols-2 divide-x divide-line",
        compact ? "gap-4" : "gap-6",
      )}
    >
      {[
        ["论文总数", scholar.metrics?.paper_count],
        ["总引用次数", scholar.metrics?.citation_count],
      ].map(([label, value]) => (
        <div key={String(label)} className="min-w-0 pl-4 first:pl-0">
          <dt className="text-xs text-muted">{label}</dt>
          <dd
            className={cn(
              "mt-1.5 break-words font-semibold tabular-nums tracking-tight text-ink",
              compact ? "text-lg" : "text-3xl",
              typeof value !== "number" && "text-sm font-normal text-muted",
            )}
          >
            {formatScholarMetric(typeof value === "number" ? value : null)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ScholarLoading({ cards = false }: { cards?: boolean }) {
  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">正在加载学者资料…</span>
      <div className={cn("grid gap-5", cards && "md:grid-cols-2")}>
        {Array.from({ length: cards ? 6 : 2 }, (_, i) => (
          <div
            key={i}
            className="animate-pulse rounded-2xl border border-line bg-card p-6"
          >
            <div className="flex gap-4">
              <div className="size-16 rounded-full bg-chip" />
              <div className="flex-1 space-y-3 py-2">
                <div className="h-4 w-1/2 rounded bg-chip" />
                <div className="h-3 w-3/4 rounded bg-chip" />
              </div>
            </div>
            <div className="mt-5 h-16 rounded-lg bg-chip" />
            <div className="mt-5 h-6 w-1/2 rounded bg-chip" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScholarError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-2xl border border-line bg-card px-6 py-12 text-center"
    >
      <AlertCircle className="mx-auto size-7 text-muted" />
      <h2 className="mt-4 font-semibold text-ink">学者数据加载失败</h2>
      <p className="mt-2 text-sm text-muted">暂时无法读取演示资料，请重试。</p>
      <Button className="mt-5" variant="outline" onClick={onRetry}>
        <RotateCw />
        重试
      </Button>
    </div>
  );
}
