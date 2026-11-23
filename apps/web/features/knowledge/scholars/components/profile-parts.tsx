"use client";

import Image from "next/image";
import { useState } from "react";
import { AlertCircle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  formatScholarMetric,
  scholarAvatarSource,
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
  const src = scholarAvatarSource(scholar.avatar_path, failedSrc);
  return (
    <span
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-primary/10 bg-primary-soft font-medium tracking-wide text-primary",
        large
          ? "size-20 text-2xl sm:size-28 sm:text-3xl"
          : "size-12 text-lg sm:size-14 sm:text-xl",
      )}
    >
      {src ? (
        <Image
          src={src}
          alt={`${scholarName(scholar)}的头像`}
          fill
          sizes={large ? "112px" : "56px"}
          unoptimized
          className="object-cover"
          onError={() => setFailedSrc(src)}
        />
      ) : (
        <span aria-label={`${scholarName(scholar)}的占位头像`}>
          {scholarInitials(scholar.name_en || scholar.name_zh)}
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
    return <p className="text-sm text-muted">机构信息暂无数据</p>;
  return (
    <div
      className={cn(
        "space-y-1 text-sm leading-relaxed text-ink-2",
        compact && "text-[13px] leading-5",
      )}
    >
      {(compact ? affiliations.slice(0, 1) : affiliations).map((item, i) => (
        <p className="break-words" key={`${item.institution}-${i}`}>
          {item.institution?.trim()}
          {item.position?.trim() ? (
            <span className="text-muted">
              {item.institution?.trim() ? " · " : ""}
              {item.position.trim()}
            </span>
          ) : null}
        </p>
      ))}
    </div>
  );
}

export function ScholarTopics({ topics }: { topics: string[] }) {
  return (
    <ul aria-label="研究主题" className="mt-3 flex flex-wrap gap-2">
      {topics.map((topic) => (
        <li key={topic} className="max-w-full break-words rounded-md border border-line px-2.5 py-1 text-xs text-primary">
          {topic}
        </li>
      ))}
    </ul>
  );
}

export function ScholarMetrics({
  scholar,
  compact = false,
  sidebar = false,
}: {
  scholar: ScholarProfile;
  compact?: boolean;
  sidebar?: boolean;
}) {
  const metrics = scholar.metrics;
  const items = [
    { label: "收录作品", value: metrics?.source_work_count },
    { label: "总引用次数", value: metrics?.citation_count },
    { label: "h 指数", value: metrics?.h_index },
    { label: "i10 指数", value: metrics?.i10_index },
  ];

  return (
    <dl
      className={cn(
        sidebar ? "grid grid-cols-2 gap-x-4 gap-y-3" : "flex flex-wrap gap-x-6 gap-y-2",
      )}
    >
      {items.map(({ label, value }) => {
        const formatted = formatScholarMetric(value);
        return (
          <div
            key={label}
            className={cn("min-w-0", compact && "flex items-baseline gap-2")}
          >
            <dt className={cn("text-xs text-muted", compact && "order-2")}>
              {label}
            </dt>
            <dd
              className={cn(
                "break-words font-semibold tabular-nums tracking-tight text-ink",
                compact ? "text-base" : "mt-0.5 text-xl leading-7",
                formatted === "暂无数据" && "text-sm font-normal text-muted",
              )}
            >
              {formatted}
            </dd>
          </div>
        );
      })}
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
            className="animate-pulse rounded-xl border border-line bg-card p-5"
          >
            <div className="flex gap-4">
              <div className="size-14 rounded-full bg-chip" />
              <div className="flex-1 space-y-3 py-2">
                <div className="h-4 w-1/2 rounded bg-chip" />
                <div className="h-3 w-3/4 rounded bg-chip" />
              </div>
            </div>
            <div className="mt-4 h-10 rounded bg-chip" />
            <div className="mt-4 h-5 w-1/2 rounded bg-chip" />
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
      <p className="mt-2 text-sm text-muted">暂时无法读取学者资料，请重试。</p>
      <Button className="mt-5" variant="outline" onClick={onRetry}>
        <RotateCw />
        重试
      </Button>
    </div>
  );
}
