"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import { cn } from "@/lib/utils";
import {
  INITIAL_PAGE_COUNT,
  initialRenderedPageCount,
  nextRenderedPageCount,
} from "./pdf-pagination";
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export function PdfDocumentView({
  file,
  width,
  numPages,
  scrollRootRef,
  onLoadSuccess,
  onLoadError,
  onFirstPageReady,
  className,
}: {
  file: string;
  width: number;
  numPages: number | null;
  scrollRootRef: RefObject<HTMLElement | null>;
  onLoadSuccess: (value: { numPages: number }) => void;
  onLoadError: (error: Error) => void;
  onFirstPageReady: () => void;
  className?: string;
}) {
  const [renderCount, setRenderCount] = useState(() => (
    initialRenderedPageCount(numPages ?? INITIAL_PAGE_COUNT)
  ));
  const sentinelRef = useRef<HTMLDivElement>(null);
  const firstReadyFileRef = useRef<string | null>(null);
  const visiblePageCount = Math.min(numPages ?? 0, renderCount);
  const pageNumbers = Array.from({ length: visiblePageCount }, (_, index) => index + 1);

  const handleFirstPageReady = useCallback(() => {
    if (firstReadyFileRef.current === file) return;
    firstReadyFileRef.current = file;
    onFirstPageReady();
  }, [file, onFirstPageReady]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !numPages || renderCount >= numPages) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (!entry?.isIntersecting) return;
      setRenderCount((current) => nextRenderedPageCount(current, numPages));
    }, {
      root: scrollRootRef.current,
      rootMargin: "1000px 0px",
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [numPages, renderCount, scrollRootRef]);

  return (
    <>
      <style>{`
        .pdf-viewer-page {
          position: relative;
          background: #fff;
          box-shadow: var(--shadow-card);
        }

        .pdf-viewer-page .textLayer {
          z-index: 1;
        }

        .pdf-viewer-page .textLayer span,
        .pdf-viewer-page .textLayer br {
          color: transparent !important;
          text-shadow: none !important;
        }

        .pdf-viewer-page .textLayer ::selection {
          background: rgb(96 165 250 / 0.22);
        }
      `}</style>
      <Document
        file={file}
        className={cn("flex min-w-full flex-col gap-6", className)}
        onLoadSuccess={onLoadSuccess}
        onLoadError={onLoadError}
        loading={null}
        error={null}
      >
        {pageNumbers.map((pageNumber) => (
          <Page
            key={pageNumber}
            pageNumber={pageNumber}
            width={width}
            className="pdf-viewer-page isolate"
            renderTextLayer={true}
            renderAnnotationLayer={false}
            onRenderSuccess={pageNumber === 1 ? handleFirstPageReady : undefined}
          />
        ))}
        {numPages !== null && renderCount < numPages && (
          <div ref={sentinelRef} aria-hidden="true" className="h-px w-full" />
        )}
      </Document>
    </>
  );
}
