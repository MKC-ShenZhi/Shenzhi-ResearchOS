"use client";

import Link from "next/link";
import { KnowledgeClientError } from "@/clients/knowledge";
import { useKnowledgePaper } from "@/features/knowledge/paper/use-knowledge-paper";
import { KnowledgePaperSkeleton } from "@/features/knowledge/paper/components/paper-skeleton";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { PaperTopbar } from "./components/paper-topbar";
import { PaperLeftSidebar } from "./components/paper-left-sidebar";
import { PaperPdfViewer } from "./components/paper-pdf-viewer";
import { PaperRightPanel } from "./components/right-panel";

export function PaperDetailPage({ paperId, returnTo }: { paperId: string; returnTo?: string | null }) {
  const { data: paper, isPending, isError, error, refetch } = useKnowledgePaper(paperId);
  const safeReturnTo = normalizeInternalReturnTo(returnTo);

  return (
    <div className="flex min-h-dvh flex-col bg-background lg:h-dvh lg:overflow-hidden">
      {paper ? <PaperTopbar paper={paper} returnTo={safeReturnTo} /> : (
        <header className="border-b border-line bg-card px-5 py-4">
          <Link href={safeReturnTo ?? "/knowledge/search"} className="text-sm text-primary">返回来源</Link>
        </header>
      )}
      {isPending && <KnowledgePaperSkeleton />}
      {isError && (
        <div role="alert" className="p-8 text-center text-sm text-muted">
          <p>{error instanceof KnowledgeClientError && error.code === "NOT_FOUND" ? "未找到这篇论文" : "论文详情加载失败"}</p>
          <p className="mt-2">{error instanceof Error ? error.message : "请稍后重试"}</p>
          <button onClick={() => void refetch()} className="mt-4 text-primary">重新加载</button>
        </div>
      )}
      {paper && (
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <PaperLeftSidebar key={`metadata-${paperId}`} paper={paper} />
          <main className="min-w-0 flex-1 p-3 lg:overflow-y-auto lg:p-5">
            <PaperPdfViewer key={paper.pdfUrl} pdfUrl={paper.pdfUrl} title={paper.title} />
          </main>
          <PaperRightPanel key={`assistant-${paperId}`} paper={paper} />
        </div>
      )}
    </div>
  );
}
