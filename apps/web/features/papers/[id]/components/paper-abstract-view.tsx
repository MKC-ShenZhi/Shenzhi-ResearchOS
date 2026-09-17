import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Badge } from "@/components/ui/badge";
import { paperDoiUrl } from "@/lib/navigation/paper";

export function PaperAbstractView({ paper }: { paper: KnowledgePaperDetail }) {
  const doiUrl = paperDoiUrl(paper.doi);

  return (
    <section
      aria-label={`${paper.title} 摘要`}
      className="mx-auto min-h-full w-full max-w-4xl px-6 py-10 lg:px-10 lg:py-12"
    >
      <header>
        <h1 className="text-2xl font-semibold leading-tight text-ink lg:text-3xl">{paper.title}</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          {paper.authors.length ? paper.authors.join(" · ") : "未知作者"}
        </p>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs leading-5 text-faint">
          <span>{paper.venue ?? "暂无会议"} · {paper.year ?? "—"}</span>
          <span>被引用：{paper.citationCount?.toLocaleString() ?? "暂无数据"}</span>
          <span>参考文献：{paper.referenceCount?.toLocaleString() ?? "暂无数据"}</span>
          {doiUrl && (
            <a href={doiUrl} target="_blank" rel="noreferrer" className="break-all text-primary hover:underline">
              DOI：{paper.doi}
            </a>
          )}
        </div>
      </header>

      <div className="mt-12 max-w-3xl">
        <h2 className="text-base font-semibold text-ink">Abstract</h2>
        <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-muted">
          {paper.abstract?.trim() || "当前论文暂无摘要"}
        </p>
      </div>
      {(paper.keywords.length > 0 || paper.subjects.length > 0) && (
        <section className="mt-10 max-w-3xl border-t border-line pt-5">
          <h3 className="mb-3 text-sm font-semibold text-ink">关键词与学科</h3>
          <div className="flex flex-wrap gap-2">
            {paper.keywords.map((word) => <Badge key={word} variant="violet">{word}</Badge>)}
            {paper.subjects.map((word) => <Badge key={word} variant="amber">{word}</Badge>)}
          </div>
        </section>
      )}
    </section>
  );
}
