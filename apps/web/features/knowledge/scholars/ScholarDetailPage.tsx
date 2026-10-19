"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, UserRound } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { useScholarProvider } from "./provider";
import { scholarName } from "./presentation";
import { AnnualCitations } from "./components/annual-citations";
import { ScholarPublications } from "./components/scholar-publications";
import {
  Affiliations,
  DemoBadge,
  ScholarAvatar,
  ScholarError,
  ScholarLoading,
  ScholarMetrics,
} from "./components/profile-parts";

export function ScholarDetailPage({
  scholarId,
  returnTo,
}: {
  scholarId: string;
  returnTo?: string | null;
}) {
  const provider = useScholarProvider();
  const safeReturnTo =
    normalizeInternalReturnTo(returnTo) ?? "/knowledge/scholars";
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["scholars-v2", provider.cacheKey, "detail", scholarId],
    queryFn: ({ signal }) => provider.detail(scholarId, signal),
  });
  const backLink = (
    <Link
      href={safeReturnTo}
      className="inline-flex items-center gap-2 text-sm text-muted transition-colors hover:text-primary focus-visible:outline-2 focus-visible:outline-primary"
    >
      <ArrowLeft className="size-4" />
      返回学者库
    </Link>
  );

  if (isPending)
    return (
      <div className="mx-auto max-w-[1200px] space-y-7 px-5 py-8 sm:px-8 lg:py-10 xl:px-12">
        {backLink}
        <ScholarLoading />
      </div>
    );
  if (isError)
    return (
      <div className="mx-auto max-w-[1200px] space-y-7 px-5 py-8 sm:px-8 lg:py-10 xl:px-12">
        {backLink}
        <ScholarError onRetry={() => void refetch()} />
      </div>
    );
  if (!data)
    return (
      <div className="mx-auto max-w-[1200px] px-5 py-8 sm:px-8 lg:py-10 xl:px-12">
        {backLink}
        <div
          role="status"
          className="my-10 rounded-2xl border border-line bg-card px-6 py-20 text-center"
        >
          <UserRound className="mx-auto size-9 text-faint" />
          <p className="mt-5 text-xs uppercase tracking-widest text-muted">
            Not Found
          </p>
          <h1 className="mt-2 text-xl font-semibold text-ink">未找到该学者</h1>
          <p className="mt-3 text-sm text-muted">
            此标识没有对应的演示资料，请返回学者库重新选择。
          </p>
          <Link
            href={safeReturnTo}
            className={buttonVariants({
              variant: "outline",
              className: "mt-6",
            })}
          >
            返回学者库
          </Link>
        </div>
      </div>
    );

  const { scholar, papers } = data;
  const hasChineseBio = Boolean(scholar.bio_zh?.trim());
  const hasEnglishBio = Boolean(scholar.bio_en?.trim());
  const updatedAt =
    scholar.updated_at && Number.isFinite(Date.parse(scholar.updated_at))
      ? scholar.updated_at
      : null;
  return (
    <div className="mx-auto w-full max-w-[1200px] px-5 py-8 sm:px-8 lg:py-10 xl:px-12">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {backLink}
        <DemoBadge />
      </div>
      <header className="mt-8 flex flex-col gap-5 border-b border-line pb-8 sm:flex-row sm:items-center sm:gap-7">
        <ScholarAvatar scholar={scholar} large />
        <div className="min-w-0 flex-1">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-primary">
            Researcher profile
          </p>
          <h1 className="break-words text-3xl font-semibold tracking-tight text-ink">
            {scholarName(scholar)}
          </h1>
          {scholar.name_zh?.trim() && scholar.name_en?.trim() ? (
            <p className="mt-1.5 break-words text-lg text-muted">
              {scholar.name_en}
            </p>
          ) : null}
          <div className="mt-4">
            <Affiliations scholar={scholar} />
          </div>
        </div>
      </header>
      <div className="mt-7 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <section
          className="min-w-0 rounded-2xl border border-line bg-card p-5 sm:p-7"
          aria-labelledby="about-title"
        >
          <h2
            id="about-title"
            className="text-lg font-semibold tracking-tight text-ink"
          >
            关于学者{" "}
            <span className="ml-2 text-sm font-normal text-muted">About</span>
          </h2>
          {hasChineseBio ? (
            <p className="mt-4 whitespace-pre-line break-words text-sm leading-7 text-ink-2">
              {scholar.bio_zh}
            </p>
          ) : null}
          {hasEnglishBio ? (
            <p
              lang="en"
              className={`whitespace-pre-line break-words text-sm leading-7 ${hasChineseBio ? "mt-4 border-t border-line pt-4 text-muted" : "mt-4 text-ink-2"}`}
            >
              {scholar.bio_en}
            </p>
          ) : null}
          {!hasChineseBio && !hasEnglishBio ? (
            <p className="mt-4 text-sm text-muted">个人简介暂无数据。</p>
          ) : null}
        </section>
        <aside
          className="min-w-0 space-y-6 xl:col-start-2 xl:row-start-1 xl:row-span-2"
          aria-label="学术统计"
        >
          <section className="rounded-2xl border border-line bg-card p-5 sm:p-6">
            <h2 className="mb-5 text-base font-semibold text-ink">学术指标</h2>
            <ScholarMetrics scholar={scholar} />
            <p className="mt-4 text-[11px] leading-5 text-muted">
              论文总数为去重论文数；总引用独立于年度引用统计。
            </p>
          </section>
          <AnnualCitations data={scholar.annual_citations} />
        </aside>
        <div className="min-w-0 xl:col-start-1">
          <ScholarPublications papers={papers} />
        </div>
      </div>
      <footer className="mt-8 text-center text-xs leading-6 text-muted">
        <p>人物、机构与学术统计均为虚构演示内容，未经知识底座验证。</p>
        {updatedAt ? (
          <p>
            演示资料更新于{" "}
            <time dateTime={updatedAt}>
              {new Date(updatedAt).toLocaleDateString("zh-CN", {
                timeZone: "UTC",
              })}
            </time>
          </p>
        ) : null}
      </footer>
    </div>
  );
}
