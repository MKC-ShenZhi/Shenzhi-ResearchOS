"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { paperHref, paperDoiUrl, paperExternalUrl } from "@/lib/navigation/paper";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { PaperCardLayout } from "../../papers/components/paper-card-layout";
import { toPaperCardModel } from "../../papers/paper-card-model";
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
        <div className="mt-5 grid gap-4">
          {data.items.map((paper, index) => {
            const doiUrl = paperDoiUrl(paper.doi);
            const pdfUrl = paperExternalUrl(paper.pdfUrl);
            return (
              <PaperCardLayout
                key={paper.id}
                index={index}
                paper={toPaperCardModel(paper)}
                detailHref={!provider.isDemo && paper.platform_detail ? paperHref(paper.id, { mode: "create", source: returnTo }) : undefined}
                actions={provider.isDemo ? null : (
                  <>
                    {doiUrl ? <a className="text-sm text-primary hover:underline" href={doiUrl} target="_blank" rel="noopener noreferrer">DOI 来源</a> : null}
                    {pdfUrl ? <a className="text-sm text-primary hover:underline" href={pdfUrl} target="_blank" rel="noopener noreferrer">PDF 来源</a> : null}
                    {!paper.platform_detail && !doiUrl && !pdfUrl ? <span className="text-sm text-muted">暂无可用来源</span> : null}
                  </>
                )}
              />
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
