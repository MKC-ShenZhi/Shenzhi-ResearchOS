"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Badge } from "@/components/ui/badge";

/** Metadata summary; no fabricated PDF outline, page count or thumbnails. */
export function PaperLeftSidebar({ paper }: { paper: KnowledgePaperDetail }) {
  const [open, setOpen] = useState(true);
  return (
    <aside className="shrink-0 border-b border-line bg-card lg:flex lg:min-h-0 lg:border-r lg:border-b-0">
      {open && (
        <div className="max-h-80 overflow-y-auto p-5 lg:max-h-none lg:w-64">
          <h2 className="text-sm font-semibold text-ink">摘要</h2>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted">{paper.abstract?.trim() || "当前论文暂无摘要"}</p>
          {(paper.keywords.length > 0 || paper.subjects.length > 0) && (
            <section className="mt-5 border-t border-line pt-4">
              <h2 className="mb-3 text-sm font-semibold text-ink">关键词与学科</h2>
              <div className="flex flex-wrap gap-2">
                {paper.keywords.map((word) => <Badge key={word} variant="violet">{word}</Badge>)}
                {paper.subjects.map((word) => <Badge key={word} variant="amber">{word}</Badge>)}
              </div>
            </section>
          )}
        </div>
      )}
      <button type="button" aria-label={open ? "折叠摘要" : "展开摘要"} aria-expanded={open} onClick={() => setOpen(!open)} className="p-2 text-muted lg:self-center">
        {open ? <ChevronLeft className="size-4" /> : <ChevronRight className="size-4" />}
      </button>
    </aside>
  );
}
