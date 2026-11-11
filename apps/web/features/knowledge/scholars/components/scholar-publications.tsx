"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { paperHref, paperDoiUrl, paperExternalUrl } from "@/lib/navigation/paper";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { knowledgeQueryRetry } from "../../retry";
import { useScholarProvider } from "../provider";
import { ScholarError, ScholarLoading } from "./profile-parts";

/** Real publication failures do not hide the profile, and never fall back to fixtures. */
export function ScholarPublications({ scholarId }: { scholarId: string }) {
  const provider = useScholarProvider();
  const returnTo = useCurrentInternalPath();
  const [page, setPage] = useState(1);
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["scholars-v2", provider.cacheKey, "papers", scholarId, page],
    queryFn: ({ signal }) => provider.papers(scholarId, 20, (page - 1) * 20, signal),
    retry: knowledgeQueryRetry,
    staleTime: 120_000,
  });
  return (
    <section className="min-w-0" aria-labelledby="publications-title">
      <h2 id="publications-title" className="text-lg font-semibold tracking-tight text-ink">
        论文成果 <span className="ml-2 text-sm font-normal tabular-nums text-muted">{data ? `共 ${data.total} 篇` : ""}</span>
      </h2>
      <p className="mt-2 text-xs leading-6 text-muted">
        {provider.isDemo ? "Mock 论文关联仅供演示，不代表真实作者关系。" : "展示知识底座已关联的论文；平台关联论文数不代表 OpenAlex 作品总数。"}
      </p>
      {isPending ? <ScholarLoading /> : isError ? <ScholarError onRetry={() => void refetch()} /> : data.items.length ? (
        <div className="mt-2 divide-y divide-line">
          {data.items.map((paper) => {
            const doiUrl = paperDoiUrl(paper.doi);
            const pdfUrl = paperExternalUrl(paper.pdfUrl);
            return (
              <article key={paper.id} className="py-6 last:pb-0">
                <div className="flex flex-col gap-3 sm:flex-row sm:gap-7">
                  <p className="shrink-0 text-sm font-medium tabular-nums leading-7 text-muted sm:w-12">{paper.year ?? "年份暂缺"}</p>
                  <div className="min-w-0 flex-1">
                    <h3 className="break-words text-[17px] font-semibold leading-7 text-ink">
                      {!provider.isDemo && paper.platform_detail ? <Link className="hover:text-primary focus-visible:outline-2" href={paperHref(paper.id, { mode: "create", source: returnTo })}>{paper.title}</Link> : paper.title}
                    </h3>
                    {paper.venue ? <p className="mt-1 text-xs font-medium leading-5 text-primary">{paper.venue}</p> : null}
                    <p className="mt-1.5 break-words text-[13px] leading-6 text-muted">{paper.authors.length ? paper.authors.join(" · ") : "作者暂无数据"}</p>
                    {paper.abstract ? <p className="mt-3 line-clamp-2 text-sm leading-6 text-ink-2">{paper.abstract}</p> : null}
                    {!provider.isDemo ? <div className="mt-3 flex flex-wrap gap-4 text-sm text-primary">
                      {doiUrl ? <a href={doiUrl} target="_blank" rel="noopener noreferrer">DOI 来源</a> : null}
                      {pdfUrl ? <a href={pdfUrl} target="_blank" rel="noopener noreferrer">PDF 来源</a> : null}
                      {!paper.platform_detail && !doiUrl && !pdfUrl ? <span className="text-muted">暂无可用来源</span> : null}
                    </div> : null}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div role="status" className="flex min-h-40 flex-col items-center justify-center text-center">
          <FileText aria-hidden="true" className="size-8 text-faint" />
          <h3 className="mt-4 text-sm font-medium text-ink-2">暂无可展示的论文成果</h3>
          <p className="mt-2 text-xs leading-6 text-muted">当前学者暂无平台关联论文资料，不代表没有发表作品。</p>
        </div>
      )}
      {data && (data.total > 20 || page > 1) ? <nav aria-label="论文成果分页" className="mt-6 flex flex-wrap items-center gap-4">
        <Button variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>上一页</Button>
        <span className="text-sm text-muted">第 {page} 页</span>
        <Button variant="outline" disabled={page * 20 >= data.total} onClick={() => setPage(page + 1)}>下一页</Button>
      </nav> : null}
    </section>
  );
}
