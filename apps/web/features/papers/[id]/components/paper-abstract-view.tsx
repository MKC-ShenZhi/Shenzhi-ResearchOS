import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Badge } from "@/components/ui/badge";

export function PaperAbstractView({ paper }: { paper: KnowledgePaperDetail }) {
  return (
    <section
      aria-label={`${paper.title} 摘要`}
      className="min-h-96 rounded-xl border border-line bg-card p-6 lg:p-8"
    >
      <h2 className="text-base font-semibold text-ink">Abstract</h2>
      <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-muted">
        {paper.abstract?.trim() || "当前论文暂无摘要"}
      </p>
      {(paper.keywords.length > 0 || paper.subjects.length > 0) && (
        <section className="mt-8 border-t border-line pt-5">
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
