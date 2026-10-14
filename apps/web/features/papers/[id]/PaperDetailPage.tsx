"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { PanelRightOpen } from "lucide-react";
import { apiJson } from "@/clients/backend/http";
import { KnowledgeClientError } from "@/clients/knowledge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CollectionPicker } from "@/features/knowledge/papers/components/collection-picker";
import { useKnowledgePaper } from "@/features/knowledge/paper/use-knowledge-paper";
import { KnowledgePaperSkeleton } from "@/features/knowledge/paper/components/paper-skeleton";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { PaperBackButton, PaperTopbar } from "./components/paper-topbar";
import { PaperAbstractView } from "./components/paper-abstract-view";
import { PaperPdfViewer, type ViewerState } from "./components/paper-pdf-viewer";
import { PaperRightPanel } from "./components/right-panel";

type PaperViewMode = "abstract" | "paper";

const DEFAULT_ASSISTANT_WIDTH_PERCENT = 42;
const MIN_READER_WIDTH = 420;
const MIN_ASSISTANT_WIDTH = 360;
const RESIZER_WIDTH = 12;
const LAYOUT_INLINE_PADDING = 12;

function clampAssistantWidthPercent(percent: number, availableWidth: number) {
  const minPercent = (MIN_ASSISTANT_WIDTH / availableWidth) * 100;
  const maxPercent = Math.min(
    58,
    ((availableWidth - MIN_READER_WIDTH) / availableWidth) * 100,
  );
  return Math.min(maxPercent, Math.max(minPercent, percent));
}

export function PaperDetailPage({ paperId, returnTo }: { paperId: string; returnTo?: string | null }) {
  const { data: paper, isPending, isError, error, refetch } = useKnowledgePaper(paperId);
  const safeReturnTo = normalizeInternalReturnTo(returnTo);
  const [viewMode, setViewMode] = useState<PaperViewMode>("abstract");
  const [hasOpenedPaper, setHasOpenedPaper] = useState(false);
  const [assistantCollapsed, setAssistantCollapsed] = useState(false);
  const [assistantWidthPercent, setAssistantWidthPercent] = useState(DEFAULT_ASSISTANT_WIDTH_PERCENT);
  const [isResizing, setIsResizing] = useState(false);
  const layoutRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [viewerState, setViewerState] = useState<ViewerState>("loading");

  const resizeAssistant = (clientX: number) => {
    const bounds = layoutRef.current?.getBoundingClientRect();
    if (!bounds) return;

    const availableWidth =
      bounds.width - 2 * LAYOUT_INLINE_PADDING - RESIZER_WIDTH;
    if (availableWidth <= 0) return;

    const assistantWidth =
      bounds.right -
      LAYOUT_INLINE_PADDING -
      clientX -
      RESIZER_WIDTH / 2;
    setAssistantWidthPercent(
      clampAssistantWidthPercent((assistantWidth / availableWidth) * 100, availableWidth),
    );
  };

  const handleResizeKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const bounds = layoutRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const availableWidth =
      bounds.width - 2 * LAYOUT_INLINE_PADDING - RESIZER_WIDTH;
    if (availableWidth <= 0) return;
    const change = event.key === "ArrowRight" ? -2 : 2;
    setAssistantWidthPercent(
      clampAssistantWidthPercent(assistantWidthPercent + change, availableWidth),
    );
  };

  const handleViewModeChange = (nextMode: string) => {
    if (nextMode !== "abstract" && nextMode !== "paper") return;
    setViewMode(nextMode);
    if (nextMode === "paper") setHasOpenedPaper(true);
  };

  const loadedPaperId = paper?.id ?? null;

  useEffect(() => {
    if (!loadedPaperId) return;
    // 进入论文详情页（含“立即阅读”）即记录浏览行为。
    // 仅登录用户会被后端写入，未登录返回 401，此处静默忽略，不影响阅读。
    void apiJson(`/papers/${encodeURIComponent(loadedPaperId)}/view`, { method: "POST" }).catch(() => {});
  }, [loadedPaperId]);

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
          <div
            ref={layoutRef}
            data-assistant-collapsed={assistantCollapsed}
            data-resizing={isResizing}
            className="paper-detail-layout flex min-h-0 flex-1 flex-col lg:p-3"
            style={{ "--assistant-width": `${assistantWidthPercent}%` } as CSSProperties}
          >
            <div className="flex min-h-0 min-w-0 flex-col lg:overflow-hidden">
              <PaperTopbar
                paper={paper}
                returnTo={safeReturnTo}
                viewMode={viewMode}
                viewerState={!paper.pdfUrl ? "no_pdf" : viewerState}
                zoom={zoom}
                setZoom={setZoom}
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  <CollectionPicker paperId={paper.id} iconOnly />
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
                </div>
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
            {!assistantCollapsed && (
              <div
                role="separator"
                aria-label="调整论文阅读器和 Assistant 面板宽度"
                aria-orientation="vertical"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(assistantWidthPercent)}
                tabIndex={0}
                className="paper-layout-resizer hidden lg:flex"
                onKeyDown={handleResizeKeyDown}
                onPointerDown={(event) => {
                  event.preventDefault();
                  event.currentTarget.setPointerCapture(event.pointerId);
                  setIsResizing(true);
                  resizeAssistant(event.clientX);
                }}
                onPointerMove={(event) => {
                  if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                    resizeAssistant(event.clientX);
                  }
                }}
                onPointerUp={(event) => {
                  if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                    event.currentTarget.releasePointerCapture(event.pointerId);
                  }
                  setIsResizing(false);
                }}
                onLostPointerCapture={() => setIsResizing(false)}
              >
                <span aria-hidden="true" />
              </div>
            )}
            <PaperRightPanel
              key={`assistant-${paperId}`}
              paper={paper}
              onCollapse={() => setAssistantCollapsed(true)}
            />
            {assistantCollapsed && (
              <div className="flex min-h-12 items-center justify-center border-t border-line bg-card lg:min-h-0 lg:items-start lg:justify-end lg:rounded-xl lg:border lg:pr-3 lg:pt-2">
                <button
                  type="button"
                  aria-label="展开 Assistant"
                  title="展开 Assistant"
                  className="inline-flex size-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-primary-soft hover:text-primary"
                  onClick={() => {
                    setAssistantWidthPercent(DEFAULT_ASSISTANT_WIDTH_PERCENT);
                    setAssistantCollapsed(false);
                  }}
                >
                  <PanelRightOpen className="size-[18px]" />
                </button>
              </div>
            )}
          </div>
        </Tabs>
      )}
    </div>
  );
}
