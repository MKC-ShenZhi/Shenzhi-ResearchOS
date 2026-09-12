"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { ArrowLeft, Download, Network, ZoomIn, ZoomOut } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { apiPath } from "@/clients/backend/http";
import { cn } from "@/lib/utils";
import { paperHref } from "@/lib/navigation/paper";
import { navigateBackFromPaper } from "../paper-back-navigation";
import type { ViewerState } from "./paper-pdf-viewer";

export function PaperBackButton({ returnTo }: { returnTo?: string | null }) {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => navigateBackFromPaper(router, returnTo)}
      aria-label="返回"
      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-1.5 py-1.5 text-sm text-muted transition-colors hover:bg-chip hover:text-ink-2"
    >
      <ArrowLeft className="size-[18px]" />
      返回
    </button>
  );
}

export function PaperTopbar({
  paper,
  returnTo,
  viewMode,
  viewerState,
  zoom,
  setZoom,
  children,
}: {
  paper: KnowledgePaperDetail;
  returnTo?: string | null;
  viewMode: "abstract" | "paper";
  viewerState: ViewerState;
  zoom: number;
  setZoom: Dispatch<SetStateAction<number>>;
  children: ReactNode;
}) {
  const pdfPath = apiPath(
    `/paper-resource/pdf?paperId=${encodeURIComponent(paper.id)}`,
  );
  const controlsVisible = viewMode === "paper" && viewerState !== "unavailable" && viewerState !== "no_pdf";
  const controlsDisabled = viewerState === "loading" || viewerState === "rendering";
  const zoomOutDisabled = !controlsVisible || controlsDisabled || zoom <= 0.75;
  const zoomInDisabled = !controlsVisible || controlsDisabled || zoom >= 2.5;
  const downloadDisabled = !controlsVisible || controlsDisabled;
  const controlButtonClass = "size-9 rounded-lg text-muted transition-colors hover:bg-primary-soft hover:text-primary [&_svg]:size-[18px]";

  return (
    <header className="grid h-14 shrink-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-1 border-b border-line/70 bg-card px-2 sm:px-3">
      <PaperBackButton returnTo={returnTo} />
      <div className="min-w-0 justify-self-center">{children}</div>
      <div className="flex min-w-0 items-center gap-1">
        {controlsVisible && (
          <div className="flex shrink-0 items-center gap-0.5">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Zoom Out"
              title="Zoom Out"
              disabled={zoomOutDisabled}
              className={controlButtonClass}
              onClick={() => setZoom((prev) => Math.max(0.75, prev - 0.1))}
            >
              <ZoomOut />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Zoom In"
              title="Zoom In"
              disabled={zoomInDisabled}
              className={controlButtonClass}
              onClick={() => setZoom((prev) => Math.min(2.5, prev + 0.1))}
            >
              <ZoomIn />
            </Button>
            <a
              href={pdfPath}
              download="paper.pdf"
              aria-label="Download PDF"
              title="Download PDF"
              aria-disabled={downloadDisabled}
              tabIndex={downloadDisabled ? -1 : undefined}
              onClick={(event) => {
                if (downloadDisabled) event.preventDefault();
              }}
              className={cn(
                controlButtonClass,
                "inline-flex items-center justify-center transition-colors",
                downloadDisabled && "pointer-events-none opacity-50",
              )}
            >
              <Download />
            </a>
          </div>
        )}
        <Link
          href={paperHref(paper.id, { mode: "preserve", returnTo, graph: true })}
          aria-label="关系图谱"
          title="关系图谱"
          className="ml-auto inline-flex size-9 shrink-0 items-center justify-center gap-1 rounded-lg px-1.5 text-sm text-muted transition-colors hover:bg-chip hover:text-primary sm:w-auto sm:justify-start sm:px-2"
        >
          <Network className="size-[18px]" />
          <span className="hidden sm:inline">关系图谱</span>
        </Link>
      </div>
    </header>
  );
}
