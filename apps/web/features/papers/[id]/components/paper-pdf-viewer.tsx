"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Highlighter,
  Loader2,
  Minus,
  Plus,
  RotateCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiPath } from "@/clients/backend/http";
import { cn } from "@/lib/utils";
import { paperExternalUrl } from "@/lib/navigation/paper";
import type {
  HighlightColor,
  PdfHighlight,
  PdfSelection,
  PdfTextRange,
} from "./pdf-text-range";
import { readPdfTextSelection } from "./pdf-text-range";

const PdfDocumentView = dynamic(
  () => import("./pdf-document-view").then((module) => module.PdfDocumentView),
  { ssr: false },
);

type ViewerState =
  | "loading"
  | "rendering"
  | "ready"
  | "external_only"
  | "unavailable"
  | "no_pdf";

function ExternalSourceLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-primary hover:underline"
    >
      在新窗口打开 PDF <ExternalLink className="size-3" />
    </a>
  );
}

function StatePanel({
  children,
  icon = <FileText className="size-8 text-faint" />,
}: {
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex min-h-96 flex-1 flex-col items-center justify-center gap-3 p-8 text-center text-sm text-muted">
      {icon}
      {children}
    </div>
  );
}

function isOpenReviewSource(value: string | null) {
  if (!value) return false;

  return new URL(value).hostname.toLowerCase() === "openreview.net";
}

const HIGHLIGHT_COLOR_OPTIONS: Array<{
  color: HighlightColor;
  label: string;
  dotClass: string;
}> = [
  { color: "yellow", label: "黄色", dotClass: "bg-yellow-300" },
  { color: "red", label: "红色", dotClass: "bg-red-300" },
  { color: "blue", label: "蓝色", dotClass: "bg-blue-300" },
  { color: "green", label: "绿色", dotClass: "bg-green-300" },
];

function textRangesOverlap(left: PdfTextRange, right: PdfTextRange) {
  return left.pageNumber === right.pageNumber && left.start < right.end && right.start < left.end;
}

export function PaperPdfViewer({
  paperId,
  pdfUrl,
  title,
}: {
  paperId: string;
  pdfUrl: string | null;
  title: string;
}) {
  const externalUrl = paperExternalUrl(pdfUrl);
  const isExternalOnly = isOpenReviewSource(externalUrl);
  const [state, setState] = useState<ViewerState>(() => {
    if (!pdfUrl) return "no_pdf";
    return isExternalOnly ? "external_only" : "loading";
  });
  const [pageNumber, setPageNumber] = useState(1);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageInputValue, setPageInputValue] = useState("1");
  const [zoom, setZoom] = useState(1);
  const [contentWidth, setContentWidth] = useState(0);
  const [selectedColor, setSelectedColor] = useState<HighlightColor>("yellow");
  const [pendingSelection, setPendingSelection] = useState<PdfSelection | null>(null);
  const [highlights, setHighlights] = useState<PdfHighlight[]>([]);
  const [retryKey, setRetryKey] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef(new Map<number, HTMLDivElement>());
  const currentPageRef = useRef(1);
  const pageInputEditingRef = useRef(false);
  const pdfPath = apiPath(`/knowledge/paper/pdf?paperId=${encodeURIComponent(paperId)}`);

  const setCurrentPage = useCallback((nextPage: number) => {
    currentPageRef.current = nextPage;
    setPageNumber(nextPage);
    if (!pageInputEditingRef.current) {
      setPageInputValue(String(nextPage));
    }
  }, []);

  const handlePageRef = useCallback((page: number, node: HTMLDivElement | null) => {
    if (node) {
      pageRefs.current.set(page, node);
    } else {
      pageRefs.current.delete(page);
    }
  }, []);

  useEffect(() => {
    const element = contentRef.current;
    if (!element || (state !== "loading" && state !== "rendering" && state !== "ready")) return;

    const updateWidth = () => setContentWidth(element.clientWidth);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, [state]);

  useEffect(() => {
    currentPageRef.current = 1;
    pageInputEditingRef.current = false;
    pageRefs.current.clear();
    setPageNumber(1);
    setPageInputValue("1");
    setNumPages(null);
    setZoom(1);
    setSelectedColor("yellow");
    setPendingSelection(null);
    setHighlights([]);
    setState(!pdfUrl ? "no_pdf" : isExternalOnly ? "external_only" : "loading");
  }, [paperId, pdfUrl, retryKey, isExternalOnly]);

  const fittedWidth = Math.max(280, contentWidth - 32);
  const pageWidth = Math.round(fittedWidth * zoom);
  const isViewerState = state === "loading" || state === "rendering" || state === "ready";
  const showViewer = Boolean(pdfUrl) && !isExternalOnly && isViewerState;
  const hasDocument = state === "rendering" || state === "ready";
  const canNavigate = Boolean(numPages) && state === "ready";

  const updatePageFromScroll = useCallback(() => {
    const container = contentRef.current;
    if (!container || pageRefs.current.size === 0) return;

    const containerRect = container.getBoundingClientRect();
    const viewportCenter = containerRect.top + containerRect.height / 2;
    let bestPage: number | null = null;
    let bestVisibleRatio = -1;
    let bestDistance = Number.POSITIVE_INFINITY;

    pageRefs.current.forEach((pageElement, candidatePage) => {
      const pageRect = pageElement.getBoundingClientRect();
      const visibleTop = Math.max(pageRect.top, containerRect.top);
      const visibleBottom = Math.min(pageRect.bottom, containerRect.bottom);
      const visibleHeight = Math.max(0, visibleBottom - visibleTop);
      if (visibleHeight === 0 || pageRect.height === 0) return;

      const visibleRatio = visibleHeight / pageRect.height;
      const distance = Math.abs((pageRect.top + pageRect.bottom) / 2 - viewportCenter);
      if (
        visibleRatio > bestVisibleRatio ||
        (visibleRatio === bestVisibleRatio && distance < bestDistance)
      ) {
        bestPage = candidatePage;
        bestVisibleRatio = visibleRatio;
        bestDistance = distance;
      }
    });

    if (bestPage !== null) setCurrentPage(bestPage);
  }, [setCurrentPage]);

  useEffect(() => {
    if (!numPages || state !== "ready") return;

    const container = contentRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(() => updatePageFromScroll(), {
      root: container,
      threshold: [0, 0.25, 0.5, 0.75, 1],
    });
    pageRefs.current.forEach((pageElement) => observer.observe(pageElement));
    container.addEventListener("scroll", updatePageFromScroll, { passive: true });
    updatePageFromScroll();

    return () => {
      observer.disconnect();
      container.removeEventListener("scroll", updatePageFromScroll);
    };
  }, [numPages, pageWidth, state, updatePageFromScroll]);

  const scrollToPage = useCallback(
    (targetPage: number) => {
      if (!numPages) return;

      const page = Math.min(numPages, Math.max(1, targetPage));
      const pageElement = pageRefs.current.get(page);
      const container = contentRef.current;
      if (!pageElement || !container) return;

      const containerRect = container.getBoundingClientRect();
      const pageRect = pageElement.getBoundingClientRect();
      container.scrollTo({
        top: container.scrollTop + pageRect.top - containerRect.top - 16,
        behavior: "smooth",
      });
      setCurrentPage(page);
    },
    [numPages, setCurrentPage],
  );

  const handleDocumentLoad = useCallback(
    ({ numPages: loadedPages }: { numPages: number }) => {
      setNumPages(loadedPages);
      setCurrentPage(Math.min(currentPageRef.current, loadedPages));
      setState("ready");
    },
    [setCurrentPage],
  );

  const handleDocumentError = useCallback((error: Error) => {
    const status = (error as Error & { status?: unknown }).status;
    if (status === 403) {
      setState("external_only");
    } else if (status === 404) {
      setState("no_pdf");
    } else {
      setState("unavailable");
    }
  }, []);

  const handlePageInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;

    event.preventDefault();
    const requestedPage = Number(event.currentTarget.value);
    if (
      numPages &&
      Number.isInteger(requestedPage) &&
      requestedPage >= 1 &&
      requestedPage <= numPages
    ) {
      scrollToPage(requestedPage);
    } else {
      setPageInputValue(String(currentPageRef.current));
    }
    event.currentTarget.blur();
  };

  const rememberSelection = () => {
    setPendingSelection(readPdfTextSelection(window.getSelection()));
  };

  const handleHighlight = (color: HighlightColor) => {
    const selection = pendingSelection ?? readPdfTextSelection(window.getSelection());
    if (!selection) return;

    setPendingSelection(selection);
    setHighlights((current) => {
      const existing = current.find((highlight) => highlight.id === selection.id);
      if (existing?.color === color) {
        return current.filter((highlight) => !textRangesOverlap(highlight, selection));
      }

      const withoutOverlaps = current.filter(
        (highlight) => highlight.id === selection.id || !textRangesOverlap(highlight, selection),
      );
      if (existing) {
        return withoutOverlaps.map((highlight) =>
          highlight.id === selection.id ? { ...highlight, color } : highlight,
        );
      }

      return [...withoutOverlaps, { ...selection, color }];
    });
  };

  return (
    <section
      aria-label={`${title} PDF 阅读区`}
      className="flex h-[75dvh] min-h-96 flex-col overflow-hidden rounded-xl border border-line bg-card lg:h-full"
    >
      {showViewer && (
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-line bg-card px-3 py-2">
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              aria-label="上一页"
              title="上一页"
              disabled={!canNavigate || pageNumber <= 1}
              onClick={() => scrollToPage(pageNumber - 1)}
            >
              <ChevronLeft />
            </Button>
            <label htmlFor="pdf-page-number" className="sr-only">
              页码
            </label>
            <input
              id="pdf-page-number"
              type="number"
              min={1}
              max={numPages ?? undefined}
              inputMode="numeric"
              aria-label="页码"
              disabled={!canNavigate}
              value={pageInputValue}
              onFocus={() => {
                pageInputEditingRef.current = true;
              }}
              onChange={(event) => setPageInputValue(event.currentTarget.value)}
              onBlur={() => {
                pageInputEditingRef.current = false;
                setPageInputValue(String(currentPageRef.current));
              }}
              onKeyDown={handlePageInputKeyDown}
              className="h-8 w-12 rounded-md border border-line bg-background px-1 text-center text-xs tabular-nums text-ink outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            />
            <span className="text-xs tabular-nums text-muted" aria-live="polite">
              / {numPages ?? "—"}
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="下一页"
              title="下一页"
              disabled={!canNavigate || !numPages || pageNumber >= numPages}
              onClick={() => scrollToPage(pageNumber + 1)}
            >
              <ChevronRight />
            </Button>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              aria-label="缩小"
              title="缩小"
              disabled={!hasDocument || zoom <= 0.75}
              onClick={() => setZoom((current) => Math.max(0.75, Number((current - 0.1).toFixed(2))))}
            >
              <Minus />
            </Button>
            <span className="min-w-12 text-center text-xs tabular-nums text-muted">
              {Math.round(zoom * 100)}%
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="放大"
              title="放大"
              disabled={!hasDocument || zoom >= 2.5}
              onClick={() => setZoom((current) => Math.min(2.5, Number((current + 0.1).toFixed(2))))}
            >
              <Plus />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="适合宽度"
              title="适合宽度"
              disabled={!hasDocument || zoom === 1}
              onClick={() => setZoom(1)}
            >
              <RotateCcw />
            </Button>
            <div className="flex items-center gap-1" role="group" aria-label="高亮颜色">
              <span className="mr-1 inline-flex items-center gap-1 text-xs text-muted">
                <Highlighter className="size-3.5" /> 高亮
              </span>
              {HIGHLIGHT_COLOR_OPTIONS.map((option) => (
                <button
                  key={option.color}
                  type="button"
                  aria-label={`${option.label}高亮`}
                  title={`${option.label}高亮`}
                  aria-pressed={selectedColor === option.color}
                  disabled={!canNavigate}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    setSelectedColor(option.color);
                    handleHighlight(option.color);
                  }}
                  className={cn(
                    "size-5 rounded-full border-2 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:pointer-events-none disabled:opacity-50",
                    option.dotClass,
                    selectedColor === option.color
                      ? "border-ink ring-2 ring-primary/40 ring-offset-1 ring-offset-card"
                      : "border-line",
                  )}
                />
              ))}
            </div>
          </div>
          {externalUrl && <ExternalSourceLink href={externalUrl} />}
        </div>
      )}

      {showViewer && (
        <div
          ref={contentRef}
          onMouseUp={rememberSelection}
          onKeyUp={rememberSelection}
          className="relative min-h-0 flex-1 overflow-auto bg-background/70 p-4"
        >
          {(state === "loading" || state === "rendering") && (
            <div className="pointer-events-none absolute inset-x-0 top-4 z-10 flex justify-center">
              <span role="status" className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-2 text-xs text-muted shadow-card">
                <Loader2 className="size-3.5 animate-spin" /> {state === "loading" ? "正在加载 PDF…" : "正在渲染 PDF…"}
              </span>
            </div>
          )}
          <PdfDocumentView
            key={`${paperId}-${retryKey}`}
            file={pdfPath}
            numPages={numPages}
            width={pageWidth}
            className={cn(zoom > 1 ? "items-start" : "items-center")}
            highlights={highlights}
            onPageRef={handlePageRef}
            onLoadSuccess={handleDocumentLoad}
            onLoadError={handleDocumentError}
          />
        </div>
      )}

      {state === "external_only" && (
        <StatePanel>
          <p>该论文来源需要在原站完成访问验证，当前暂不支持站内阅读。</p>
          {externalUrl && <ExternalSourceLink href={externalUrl} />}
        </StatePanel>
      )}

      {state === "unavailable" && (
        <StatePanel>
          <p>PDF 暂时加载或渲染失败</p>
          <Button variant="outline" size="sm" onClick={() => setRetryKey((current) => current + 1)}>
            重试
          </Button>
          {externalUrl && <ExternalSourceLink href={externalUrl} />}
        </StatePanel>
      )}

      {state === "no_pdf" && (
        <StatePanel>
          <p>当前论文暂无可用 PDF</p>
          <p className="px-5 text-xs">可继续阅读摘要与元信息，或通过 DOI 访问论文主页。</p>
        </StatePanel>
      )}
    </section>
  );
}
