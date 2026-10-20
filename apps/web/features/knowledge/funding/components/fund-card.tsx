import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { KnowledgeFundingSummary } from "@/clients/knowledge";
import { getFundCardMetadata } from "../fund-card-mock-data";
import { fundingDetailHref } from "../funding-url-state";

export function FundCard({ funding, query }: { funding: KnowledgeFundingSummary; query: string }) {
  const metadata = getFundCardMetadata(funding.id);

  return (
    <Link
      href={fundingDetailHref(funding.id, funding.name, query)}
      className="group flex h-full w-full min-w-0 flex-col rounded-2xl bg-card p-5 shadow-card transition-shadow hover:shadow-pop"
      aria-label={`查看基金：${funding.name}`}
    >
      <div className="flex items-center justify-between">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-xs font-bold text-primary">
          {metadata.agencyAbbreviation}
        </span>
        <ArrowUpRight aria-hidden="true" className="size-4 text-faint transition-colors group-hover:text-primary" />
      </div>

      <h2 className="mt-3 line-clamp-2 break-words text-base font-semibold leading-6 tracking-tight text-ink transition-colors group-hover:text-primary" title={funding.name}>
        {funding.name}
      </h2>

      <p className="mt-1 text-xs text-muted" title={`${metadata.agencyName} · ${metadata.projectType}`}>
        {metadata.agencyName} · {metadata.projectType}
      </p>

      <p className="mt-2 line-clamp-2 text-sm leading-5 text-muted" title={metadata.shortDescription}>
        {metadata.shortDescription}
      </p>

      <div className="mt-3 min-w-0">
        <p className="truncate text-sm font-medium text-ink" title={metadata.principalInvestigator}>
          {metadata.principalInvestigator}
        </p>
        <p className="truncate text-xs text-muted" title={metadata.hostInstitution}>
          {metadata.hostInstitution}
        </p>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line/50 pt-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tabular-nums text-ink" title={metadata.period}>{metadata.period}</p>
          <p className="mt-0.5 text-xs text-muted">执行周期</p>
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tabular-nums text-ink" title={metadata.fundingAmount}>{metadata.fundingAmount}</p>
          <p className="mt-0.5 text-xs text-muted">资助金额</p>
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tabular-nums text-ink">{funding.paperCount.toLocaleString()}</p>
          <p className="mt-0.5 text-xs text-muted">关联论文</p>
        </div>
      </div>
    </Link>
  );
}
