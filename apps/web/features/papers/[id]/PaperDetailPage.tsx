"use client";

import { useState } from "react";
import { KnowledgeClientError } from "@/clients/knowledge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKnowledgePaper } from "@/features/knowledge/paper/use-knowledge-paper";
import { KnowledgePaperSkeleton } from "@/features/knowledge/paper/components/paper-skeleton";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { PaperBackButton, PaperTopbar } from "./components/paper-topbar";
import { PaperAbstractView } from "./components/paper-abstract-view";
import { PaperPdfViewer, type ViewerState } from "./components/paper-pdf-viewer";
import { PaperRightPanel } from "./components/right-panel";

type PaperViewMode = "abstract" | "paper";

export function PaperDetailPage({ paperId, returnTo }: { paperId: string; returnTo?: string | null }) {
  const { data: paper, isPending, isError, error, refetch } = useKnowledgePaper(paperId);
  const safeReturnTo = normalizeInternalReturnTo(returnTo);
  const [viewMode, setViewMode] = useState<PaperViewMode>("abstract");
  const [hasOpenedPaper, setHasOpenedPaper] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [viewerState, setViewerState] = useState<ViewerState>("loading");

  const handleViewModeChange = (nextMode: string) => {
    if (nextMode !== "abstract" && nextMode !== "paper") return;
    setViewMode(nextMode);
    if (nextMode === "paper") setHasOpenedPaper(true);
  };

  return (
    <div className="flex min-h-dvh flex-col bg-background lg:h-dvh lg:overflow-hidden">
      {!paper && (
        <header className="border-b border-line bg-card px-5 py-4">
          <div className="text-sm text-primary">
            <PaperBackButton returnTo={safeReturnTo} />
          </div>
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
        <Tabs
          value={viewMode}
          onValueChange={handleViewModeChange}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(26rem,42%)] lg:gap-3 lg:p-3">
            <div className="flex min-h-0 min-w-0 flex-col lg:overflow-hidden">
              <PaperTopbar
                paper={paper}
                returnTo={safeReturnTo}
                viewMode={viewMode}
                viewerState={!paper.pdfUrl ? "no_pdf" : viewerState}
                zoom={zoom}
                setZoom={setZoom}
              >
                <TabsList aria-label="论文内容" className="h-10 shrink-0 gap-0.5 rounded-full bg-chip p-1">
                  <TabsTrigger
                    value="abstract"
                    className="h-8 rounded-full px-3.5 text-base font-medium text-muted hover:bg-primary-soft hover:text-primary data-[state=active]:bg-card data-[state=active]:text-primary data-[state=active]:shadow-sm sm:px-4"
                  >
                    Abstract
                  </TabsTrigger>
                  <TabsTrigger
                    value="paper"
                    className="h-8 rounded-full px-3.5 text-base font-medium text-muted hover:bg-primary-soft hover:text-primary data-[state=active]:bg-card data-[state=active]:text-primary data-[state=active]:shadow-sm sm:px-4"
                  >
                    Paper
                  </TabsTrigger>
                </TabsList>
              </PaperTopbar>
              <main className="min-h-0 min-w-0 flex-1 lg:overflow-hidden">
                <div className="h-full min-h-0">
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
                        zoom={zoom}
                        setZoom={setZoom}
                        onViewerStateChange={setViewerState}
                      />
                    </div>
                  )}
                </div>
              </main>
            </div>
            <PaperRightPanel key={`assistant-${paperId}`} paper={paper} />
          </div>
        </Tabs>
      )}
    </div>
  );
}
