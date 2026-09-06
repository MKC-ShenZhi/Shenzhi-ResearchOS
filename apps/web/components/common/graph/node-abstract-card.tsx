import Link from "next/link";
import { ArrowRight, Quote } from "lucide-react";
import type { GraphNode } from "@/types";

/** 右栏 —— 选中节点论文的摘要卡(默认 origin) */
export function NodeAbstractCard({ node }: { node: GraphNode }) {
  return (
    <article className="space-y-3">
      <h2 className="text-[15px] font-bold leading-snug text-ink">
        {node.title}
      </h2>
      <p className="text-xs text-muted">{node.authors}</p>
      <p className="flex items-center gap-3 text-xs text-faint">
        <span>
          {node.venue} · {node.year}
        </span>
        <span className="flex items-center gap-1">
          <Quote className="size-3" />
          {node.citations}
        </span>
      </p>
      <p className="border-t border-line pt-3 text-[13px] leading-relaxed text-ink-2">
        {node.abstract}
      </p>
      {node.paperId && (
        <Link
          href={`/papers/${encodeURIComponent(node.paperId)}`}
          className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"
        >
          查看论文详情
          <ArrowRight className="size-3.5" />
        </Link>
      )}
    </article>
  );
}
