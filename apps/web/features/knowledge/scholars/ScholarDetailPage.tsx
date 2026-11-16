"use client";

import Image from "next/image";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, UserRound } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { knowledgeQueryRetry } from "../retry";
import { useScholarProvider } from "./provider";
import type { ScholarProfile } from "./types";
import { scholarName } from "./presentation";
import { ScholarBiography } from "./components/scholar-biography";
import { AnnualCitations } from "./components/annual-citations";
import { ScholarEmployment } from "./components/scholar-employment";
import { ScholarPublications } from "./components/scholar-publications";
import {
  Affiliations,
  DemoBadge,
  ScholarAvatar,
  ScholarError,
  ScholarLoading,
  ScholarMetrics,
  ScholarTopics,
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
    retry: knowledgeQueryRetry,
    staleTime: 120_000,
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

  if (!data && !isPending && !isError)
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
            未找到此学者资料，请返回学者库重新选择。
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

  const scholar = data?.scholar;
  const updatedAt =
    scholar?.updated_at && Number.isFinite(Date.parse(scholar.updated_at))
      ? scholar.updated_at
      : null;
  return (
    <div className="@container mx-auto w-full max-w-[1720px] px-5 py-8 sm:px-8 lg:py-10 xl:px-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {backLink}
        {provider.isDemo ? <DemoBadge /> : null}
      </div>
      {isPending ? (
        <div className="mt-8"><ScholarLoading /></div>
      ) : isError ? (
        <div className="mt-8"><ScholarError onRetry={() => void refetch()} /></div>
      ) : scholar ? (
        <ScholarProfileSections scholar={scholar} />
      ) : null}
      {/* Keep publications mounted while profile loading/error state changes. */}
      <div className="pt-8">
        <ScholarPublications key={scholarId} scholarId={scholarId} />
      </div>
      {scholar ? <footer className="mt-8 border-t border-line pt-5 text-xs leading-6 text-muted">
        <p>{provider.isDemo ? "人物、机构与学术统计均为虚构演示内容，未经知识底座验证。" : "学者资料来自知识底座。机构关系不代表当前任职；未提供的履历和指标不作推断。"}</p>
        {scholar.citation_meta ? <p>引用来源：{scholar.citation_meta.source || "暂无数据"}；覆盖范围：{scholar.citation_meta.coverage || "暂无数据"}；统计截至：{scholar.citation_meta.as_of || "暂无数据"}</p> : null}
        {updatedAt ? (
          <p>
            资料更新于{" "}
            <time dateTime={updatedAt}>
              {new Date(updatedAt).toLocaleDateString("zh-CN", {
                timeZone: "UTC",
              })}
            </time>
          </p>
        ) : null}
      </footer> : null}
    </div>
  );
}


function ScholarProfileSections({ scholar }: { scholar: ScholarProfile }) {
  return (
    <>
      <header className="mt-8 flex items-start gap-5 sm:gap-7">
        <ScholarAvatar scholar={scholar} large />
        <div className="min-w-0 flex-1">
          <h1 className="break-words text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-[40px]">
            {scholarName(scholar)}
          </h1>
          {scholar.name_zh?.trim() && scholar.name_en?.trim() ? (
            <p className="mt-2 break-words text-lg text-muted sm:text-xl">
              {scholar.name_en}
            </p>
          ) : null}
          {scholar.affiliations?.length ? (
            <div className="mt-4">
              <p className="mb-1 text-xs text-muted">关联机构</p>
              <Affiliations scholar={scholar} />
            </div>
          ) : null}
          {scholar.external_ids?.orcid ? (
            <a
              href={`https://orcid.org/${scholar.external_ids.orcid}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex max-w-full flex-wrap items-center gap-2 text-sm text-muted hover:text-primary"
            >
              <Image src="/images/orcid-id.gif" alt="" width={16} height={16} unoptimized />
              ORCID
            </a>
          ) : null}
          {scholar.topics?.length ? <ScholarTopics topics={scholar.topics} /> : null}
        </div>
      </header>
      <div className="mt-8 grid items-start gap-x-10 gap-y-6 border-t border-line pt-8 @min-[800px]:grid-cols-[minmax(0,1fr)_17rem] @min-[800px]:grid-rows-[auto_1fr] @min-[1100px]:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0 border-b border-line pb-6">
          <ScholarBiography key={scholar.scholar_id} scholar={scholar} />
        </div>
        <aside className="min-w-0 rounded-xl border border-line bg-card p-4 sm:max-w-sm @min-[800px]:col-start-2 @min-[800px]:row-span-2 @min-[800px]:row-start-1 @min-[800px]:max-w-none" aria-label="学术统计">
          <ScholarMetrics scholar={scholar} sidebar />
          <div className="mt-4 border-t border-line pt-4">
            <AnnualCitations data={scholar.annual_citations} />
          </div>
        </aside>
        {scholar.employment?.length ? (
          <div className="min-w-0 @min-[800px]:col-start-1">
            <ScholarEmployment key={`employment-${scholar.scholar_id}`} entries={scholar.employment} />
          </div>
        ) : null}
      </div>
    </>
  );
}
