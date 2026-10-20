"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getKnowledgeClient, KnowledgeClientError } from "@/clients/knowledge";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";
import { KnowledgeResultCard } from "@/features/knowledge/search/components/result-card";
import {
  KnowledgeSearchEmpty,
  KnowledgeSearchError,
  KnowledgeSearchSkeleton,
} from "@/features/knowledge/search/components/search-states";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { FUND_DETAIL_METADATA } from "./data-fund-detail";
import { fundingLibraryHref } from "./funding-url-state";

const FUNDING_RELATED_PAPER_LIMIT = 20;

export function FundDetailPage({
  fundingId,
  name,
  query,
}: {
  fundingId: string;
  name?: string | null;
  query?: string | null;
}) {
  const returnTo = useCurrentInternalPath();
  const urlName = name?.trim() || null;
  const summaryQuery = useQuery({
    queryKey: ["knowledge", "funding-restore", fundingId],
    queryFn: async () => {
      const response = await getKnowledgeClient().searchFundings({ query: fundingId, limit: 20, offset: 0 });
      return response.results.find((candidate) => candidate.id === fundingId) ?? null;
    },
    retry: knowledgeQueryRetry,
  });
  const fundingName = urlName ?? summaryQuery.data?.name ?? null;
  const relatedPaperQuery = useQuery({
    queryKey: ["knowledge", "funding-related", fundingId, fundingName],
    queryFn: () => getKnowledgeClient().searchByFunding(fundingName!, FUNDING_RELATED_PAPER_LIMIT),
    enabled: Boolean(fundingName),
    retry: knowledgeQueryRetry,
  });
  const backHref = fundingLibraryHref(query ?? "");
  const summaryError = summaryQuery.error instanceof KnowledgeClientError
    ? summaryQuery.error
    : new KnowledgeClientError("UNKNOWN", "基金信息恢复失败");
  const relatedPaperError = relatedPaperQuery.error instanceof KnowledgeClientError
    ? relatedPaperQuery.error
    : new KnowledgeClientError("UNKNOWN", "关联论文检索失败");

  if (!fundingName) {
    return (
      <main className="flex min-h-[70vh] items-center justify-center bg-background px-6 py-8">
        <div className="w-full max-w-md text-center">
          {summaryQuery.isError ? (
            <KnowledgeSearchError error={summaryError} onRetry={() => void summaryQuery.refetch()} />
          ) : summaryQuery.isPending ? (
            <div className="rounded-2xl border border-line bg-card p-8 text-sm text-muted shadow-card">
              正在恢复基金信息…
            </div>
          ) : (
            <div className="rounded-2xl border border-line bg-card p-8 shadow-card">
              <h1 className="text-lg font-semibold text-ink">无法获取基金名称</h1>
              <p className="mt-2 text-sm text-muted">当前链接没有基金名称，且暂时无法从基金列表中恢复。</p>
            </div>
          )}
          <Link href={backHref} className="mt-5 inline-flex h-9 items-center gap-2 rounded-lg border border-line bg-card px-4 text-sm font-medium text-ink-2 hover:bg-chip">
            <ArrowLeft className="size-4" />返回项目基金库
          </Link>
        </div>
      </main>
    );
  }

  const metadataRows = [
    ["项目名称", FUND_DETAIL_METADATA.projectName],
    ["项目中文名称", FUND_DETAIL_METADATA.projectNameZh],
    ["项目编号", FUND_DETAIL_METADATA.projectNumber],
    ["资助机构", FUND_DETAIL_METADATA.fundingAgency],
    ["项目类别", FUND_DETAIL_METADATA.projectCategory],
    ["项目负责人（PI）", FUND_DETAIL_METADATA.principalInvestigator],
    ["依托机构", FUND_DETAIL_METADATA.hostInstitution],
    ["资助金额", FUND_DETAIL_METADATA.fundingAmount],
    ["开始日期", FUND_DETAIL_METADATA.startDate],
    ["结束日期", FUND_DETAIL_METADATA.endDate],
    ["研究领域", FUND_DETAIL_METADATA.researchAreas],
    ["项目简介", FUND_DETAIL_METADATA.description],
    ["数据来源", FUND_DETAIL_METADATA.dataSource],
  ];

  return (
    <main className="min-h-screen bg-background px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1180px]">
        <Link href={backHref} className="inline-flex items-center gap-2 text-sm text-muted transition hover:text-primary">
          <ArrowLeft className="size-4" />返回项目基金库
        </Link>

        <header className="mt-5 rounded-2xl border border-line bg-card p-5 shadow-card sm:p-7">
          <h1 className="break-words text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-[30px]">{fundingName}</h1>
          <p className="mt-3 text-sm text-muted">
            基金编号：{fundingId}
            {summaryQuery.data ? ` · 关联论文 ${summaryQuery.data.paperCount.toLocaleString()} 篇` : ""}
          </p>
        </header>

        <section aria-labelledby="fund-metadata-title" className="mt-6 rounded-2xl border border-line bg-card p-5 shadow-card sm:p-7">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-line/70 pb-4">
            <h2 id="fund-metadata-title" className="text-xl font-semibold tracking-tight text-ink">科研基金项目元信息</h2>
            <span className="rounded-full bg-primary/8 px-3 py-1.5 text-xs font-medium text-primary">示例项目详情 · 详细数据接入中</span>
          </div>
          <dl className="grid gap-x-8 md:grid-cols-2">
            {metadataRows.map(([label, value]) => (
              <div key={label} className="grid min-w-0 grid-cols-[minmax(7rem,0.75fr)_minmax(0,1.5fr)] gap-3 border-b border-line/50 py-3.5 last:border-0 md:last:border-b">
                <dt className="text-sm text-muted">{label}</dt>
                <dd className="min-w-0 break-words text-sm leading-6 text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="fund-related-papers" className="mt-8">
          <div className="mb-4">
            <h2 id="fund-related-papers" className="text-xl font-semibold tracking-tight text-ink">关联论文</h2>
            <p className="mt-1 text-sm text-muted">
              {summaryQuery.data
                ? `基金统计 ${summaryQuery.data.paperCount.toLocaleString()} 篇 · 当前最多展示 ${FUNDING_RELATED_PAPER_LIMIT} 篇`
                : `当前最多展示 ${FUNDING_RELATED_PAPER_LIMIT} 篇`}
            </p>
          </div>
          {relatedPaperQuery.isPending ? (
            <KnowledgeSearchSkeleton count={3} />
          ) : relatedPaperQuery.isError ? (
            <KnowledgeSearchError error={relatedPaperError} onRetry={() => void relatedPaperQuery.refetch()} />
          ) : relatedPaperQuery.data?.results.length === 0 ? (
            <KnowledgeSearchEmpty query={fundingName} />
          ) : (
            <div className="space-y-4">
              {relatedPaperQuery.data?.results.map((paper, index) => (
                <KnowledgeResultCard key={paper.id} hit={paper} index={index} returnTo={returnTo} />
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
