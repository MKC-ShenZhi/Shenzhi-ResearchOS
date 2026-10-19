import { FileText } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge/types";
import { Badge } from "@/components/ui/badge";

/** 复用论文库类型与 Badge。演示 ID 尚未验证可用于真实详情，故不生成详情链接。 */
export function ScholarPublications({
  papers,
}: {
  papers: KnowledgePaperDetail[];
}) {
  return (
    <section
      className="rounded-2xl border border-line bg-card p-5 sm:p-7"
      aria-labelledby="publications-title"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2
          id="publications-title"
          className="text-lg font-semibold tracking-tight text-ink"
        >
          论文成果{" "}
          <span className="ml-2 text-sm font-normal tabular-nums text-muted">
            {papers.length} 篇展示
          </span>
        </h2>
        <span className="text-[11px] text-muted">演示关联</span>
      </div>
      <p className="mt-2 text-xs leading-6 text-muted">
        复用现有 Mock
        论文；与虚构学者的关联仅供演示，不代表真实作者关系。详情尚未联调，暂不开放跳转。
      </p>
      {papers.length ? (
        <div className="mt-2 divide-y divide-line">
          {papers.map((paper) => (
            <article key={paper.id} className="py-6 last:pb-0">
              <div className="flex gap-4">
                <span
                  aria-hidden="true"
                  className="hidden size-11 shrink-0 items-center justify-center rounded-lg border border-line bg-background sm:flex"
                >
                  <FileText className="size-5 text-primary/70" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                    {paper.year !== null ? <span>{paper.year}</span> : null}
                    {paper.venue ? (
                      <Badge variant="default">{paper.venue}</Badge>
                    ) : null}
                  </div>
                  <h3 className="break-words text-[15px] font-semibold leading-6 text-ink">
                    {paper.title}
                  </h3>
                  <p className="mt-2 break-words text-xs leading-5 text-muted">
                    {paper.authors.length
                      ? paper.authors.join(" · ")
                      : "作者暂无数据"}
                  </p>
                  {paper.abstract ? (
                    <p className="mt-3 line-clamp-3 text-[13px] leading-6 text-ink-2">
                      {paper.abstract}
                    </p>
                  ) : null}
                  <p className="mt-3 text-[11px] text-muted">
                    仅展示 · 论文详情暂不可用
                  </p>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="flex min-h-52 flex-col items-center justify-center text-center">
          <FileText aria-hidden="true" className="size-8 text-faint" />
          <h3 className="mt-4 text-sm font-medium text-ink-2">
            暂无可展示的论文成果
          </h3>
          <p className="mt-2 text-xs leading-6 text-muted">
            当前演示学者还没有关联论文资料。
          </p>
        </div>
      )}
    </section>
  );
}
