"use client";

import Link from "next/link";
import { ArrowLeft, Network } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { paperDoiUrl, paperHref } from "@/lib/navigation/paper";

export function PaperTopbar({ paper, returnTo }: { paper: KnowledgePaperDetail; returnTo?: string | null }) {
  const doiUrl = paperDoiUrl(paper.doi);
  return (
    <header className="shrink-0 border-b border-line bg-card px-5 py-3">
      <div className="flex items-center justify-between gap-4 text-xs text-primary">
        <Link href={returnTo ?? "/knowledge/search"} className="inline-flex items-center gap-1">
          <ArrowLeft className="size-4" />
          {returnTo?.startsWith("/agents") ? "返回对话" : returnTo ? "返回来源" : "返回论文检索"}
        </Link>
        <Link href={paperHref(paper.id, returnTo, true)} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-2">
          <Network className="size-4" />关系图谱
        </Link>
      </div>
      <h1 className="mt-2 text-lg font-semibold leading-snug text-ink">{paper.title}</h1>
      <p className="mt-1 text-sm text-muted">{paper.authors.length ? paper.authors.join(" · ") : "未知作者"}</p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-faint">
        <span>{paper.venue ?? "暂无会议"} · {paper.year ?? "—"}</span>
        <span>被引用：{paper.citationCount?.toLocaleString() ?? "暂无数据"}</span>
        <span>参考文献：{paper.referenceCount?.toLocaleString() ?? "暂无数据"}</span>
        {doiUrl && <a href={doiUrl} target="_blank" rel="noreferrer" className="break-all text-primary">DOI：{paper.doi}</a>}
      </div>
    </header>
  );
}
