import Link from "next/link";
import { ArrowRight, FileText } from "lucide-react";
import type { KnowledgeScholarSummary } from "@/clients/knowledge";
import { scholarHref } from "@/lib/navigation/scholar";

/** 仅展示 Scholar Search 真实返回的姓名与论文数量。 */
export function ScholarCard({ scholar }: { scholar: KnowledgeScholarSummary }) {
  return (
    <Link
      href={scholarHref(scholar.id)}
      className="group flex items-center gap-4 rounded-2xl bg-card p-5 shadow-card transition-shadow hover:shadow-pop"
    >
      <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
        <FileText className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-[15px] font-bold text-ink group-hover:text-primary">
          {scholar.name}
        </h2>
        <p className="mt-1 text-xs text-muted">收录论文 {scholar.paperCount} 篇</p>
      </div>
      <ArrowRight className="size-4 shrink-0 text-faint group-hover:text-primary" />
    </Link>
  );
}
