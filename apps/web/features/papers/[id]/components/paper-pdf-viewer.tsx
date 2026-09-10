"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ExternalLink,
  FileText,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiPath } from "@/clients/backend/http";
import { cn } from "@/lib/utils";
import { paperExternalUrl } from "@/lib/navigation/paper";

const PdfDocumentView = dynamic(
  () => import("./pdf-document-view").then((module) => module.PdfDocumentView),
  { ssr: false },
);

type ViewerState =
  | "loading"
  | "rendering"
  | "ready"
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
  const [state, setState] = useState<ViewerState>(() => {
    if (!pdfUrl) return "no_pdf";
    return "loading";
  });
  const [numPages, setNumPages] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [contentWidth, setContentWidth] = useState(0);
  const [retryKey, setRetryKey] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const pdfPath = apiPath(
    `/paper-resource/pdf?paperId=${encodeURIComponent(paperId)}`,
  );

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
    // Reset the local reader state when the displayed paper changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNumPages(null);
    setZoom(1);
    setState(!pdfUrl ? "no_pdf" : "loading");
  }, [paperId, pdfUrl, retryKey]);

  const fittedWidth = Math.max(280, contentWidth - 32);
  const pageWidth = Math.round(fittedWidth * zoom);
  const isViewerState = state === "loading" || state === "rendering" || state === "ready";
  const showViewer = Boolean(pdfUrl) && isViewerState;

  useEffect(() => {
    const element = contentRef.current;
    if (!element || !showViewer) return;

    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      setZoom((current) => Math.min(
        2.5,
        Math.max(0.75, Number((current - Math.sign(event.deltaY) * 0.1).toFixed(2))),
      ));
    };

    element.addEventListener("wheel", handleWheel, { passive: false });
    return () => element.removeEventListener("wheel", handleWheel);
  }, [showViewer]);

  const handleDocumentLoad = useCallback(({ numPages: loadedPages }: { numPages: number }) => {
    setNumPages(loadedPages);
    setState("ready");
  }, []);

  const handleDocumentError = useCallback((error: Error) => {
    const status = (error as Error & { status?: unknown }).status;
    if (status === 404) {
      setState("no_pdf");
    } else {
      setState("unavailable");
    }
  }, []);

  return (
    <section
      aria-label={`${title} PDF 阅读区`}
      className="flex h-[75dvh] min-h-96 flex-col overflow-hidden rounded-xl border border-line bg-card lg:h-full"
    >
      {showViewer && (
        <div
          ref={contentRef}
          className="relative min-h-0 flex-1 overflow-auto bg-background/70 p-4"
        >
          {(state === "loading" || state === "rendering") && (
            <div className="pointer-events-none absolute inset-x-0 top-4 z-10 flex justify-center">
              <span role="status" className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-2 text-xs text-muted shadow-card">
                <Loader2 className="size-3.5 animate-spin" /> {state === "loading" ? "正在加载论文 PDF..." : "正在渲染论文 PDF..."}
              </span>
            </div>
          )}
          <PdfDocumentView
            key={`${paperId}-${retryKey}`}
            file={pdfPath}
            numPages={numPages}
            width={pageWidth}
            className={cn(zoom > 1 ? "items-start" : "items-center")}
            onLoadSuccess={handleDocumentLoad}
            onLoadError={handleDocumentError}
          />
        </div>
      )}

      {state === "unavailable" && (
        <StatePanel>
          <p>当前论文暂无法在线加载 PDF</p>
          <Button variant="outline" size="sm" onClick={() => setRetryKey((current) => current + 1)}>
            重试
          </Button>
          {externalUrl && <ExternalSourceLink href={externalUrl} />}
        </StatePanel>
      )}

      {state === "no_pdf" && (
        <StatePanel>
          <p>当前论文暂无可用 PDF 链接</p>
          <p className="px-5 text-xs">可继续阅读摘要与元信息，或通过 DOI 访问论文主页。</p>
        </StatePanel>
      )}
    </section>
  );
}
