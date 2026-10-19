import { FileText } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge/types";

/** 复用论文库类型。演示 ID 尚未验证可用于真实详情，故不生成详情链接。 */
export function ScholarPublications({
  papers,
}: {
  papers: KnowledgePaperDetail[];
}) {
  return (
    <section className="min-w-0" aria-labelledby="publications-title">
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
        Mock 论文关联仅供演示，不代表真实作者关系。论文详情暂不可用。
      </p>
      {papers.length ? (
        <div className="mt-2 divide-y divide-line">
          {papers.map((paper) => (
            <article key={paper.id} className="py-6 last:pb-0">
              <div className="flex flex-col gap-3 sm:flex-row sm:gap-7">
                <p className="shrink-0 text-sm font-medium tabular-nums leading-7 text-muted sm:w-12">
                  {paper.year ?? "年份暂缺"}
                </p>
                <div className="min-w-0 flex-1">
                  <h3 className="break-words text-[17px] font-semibold leading-7 text-ink">
                    {paper.title}
                  </h3>
                  {paper.venue ? (
                    <p className="mt-1 text-xs font-medium leading-5 text-primary">
                      {paper.venue}
                    </p>
                  ) : null}
                  <p className="mt-1.5 break-words text-[13px] leading-6 text-muted">
                    {paper.authors.length
                      ? paper.authors.join(" · ")
                      : "作者暂无数据"}
                  </p>
                  {paper.abstract ? (
                    <p className="mt-3 line-clamp-2 text-sm leading-6 text-ink-2">
                      {paper.abstract}
                    </p>
                  ) : null}
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="flex min-h-40 flex-col items-center justify-center text-center">
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
