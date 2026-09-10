"use client";

import Link from "next/link";
import { useState } from "react";
import { KnowledgeClientError } from "@/clients/knowledge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKnowledgePaper } from "@/features/knowledge/paper/use-knowledge-paper";
import { KnowledgePaperSkeleton } from "@/features/knowledge/paper/components/paper-skeleton";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { PaperTopbar } from "./components/paper-topbar";
import { PaperAbstractView } from "./components/paper-abstract-view";
import { PaperPdfViewer } from "./components/paper-pdf-viewer";
import { PaperRightPanel } from "./components/right-panel";

type PaperViewMode = "abstract" | "paper";

export function PaperDetailPage({ paperId, returnTo }: { paperId: string; returnTo?: string | null }) {
  const { data: paper, isPending, isError, error, refetch } = useKnowledgePaper(paperId);
  const safeReturnTo = normalizeInternalReturnTo(returnTo);
  const [viewMode, setViewMode] = useState<PaperViewMode>("abstract");
  const [hasOpenedPaper, setHasOpenedPaper] = useState(false);

  const handleViewModeChange = (nextMode: string) => {
    if (nextMode !== "abstract" && nextMode !== "paper") return;
    setViewMode(nextMode);
    if (nextMode === "paper") setHasOpenedPaper(true);
  };

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
          <main className="flex min-w-0 flex-1 flex-col p-3 lg:overflow-hidden lg:p-5">
            <Tabs
              value={viewMode}
              onValueChange={handleViewModeChange}
              className="flex min-h-0 flex-1 flex-col"
            >
              <TabsList
                aria-label="论文内容"
                className="w-fit shrink-0 rounded-xl border border-line bg-card p-1"
              >
                <TabsTrigger value="abstract">Abstract</TabsTrigger>
                <TabsTrigger value="paper">Paper</TabsTrigger>
              </TabsList>
              <div className="mt-3 min-h-0 flex-1">
                {viewMode === "abstract" && (
                  <div role="tabpanel" aria-label="Abstract" className="h-full overflow-y-auto">
                    <PaperAbstractView key={`abstract-${paperId}`} paper={paper} />
                  </div>
                )}
                {hasOpenedPaper && (
                  <div
                    role="tabpanel"
                    aria-label="Paper"
                    aria-hidden={viewMode !== "paper"}
                    className={viewMode === "paper" ? "h-full" : "hidden"}
                  >
                    <PaperPdfViewer
                      key={paperId}
                      paperId={paperId}
                      pdfUrl={paper.pdfUrl}
                      title={paper.title}
                    />
                  </div>
                )}
              </div>
            </Tabs>
          </main>
          <PaperRightPanel key={`assistant-${paperId}`} paper={paper} />
        </div>
      )}
    </div>
  );
}
