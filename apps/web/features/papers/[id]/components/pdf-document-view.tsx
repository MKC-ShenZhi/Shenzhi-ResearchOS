"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import { cn } from "@/lib/utils";
import {
  INITIAL_PAGE_COUNT,
  initialRenderedPageCount,
  isFinalPageVisible,
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
  onReachedEnd,
  className,
}: {
  file: string;
  width: number;
  numPages: number | null;
  scrollRootRef: RefObject<HTMLElement | null>;
  onLoadSuccess: (value: { numPages: number }) => void;
  onLoadError: (error: Error) => void;
  onFirstPageReady: () => void;
  onReachedEnd: () => void;
  className?: string;
}) {
  const [renderCount, setRenderCount] = useState(() => (
    initialRenderedPageCount(numPages ?? INITIAL_PAGE_COUNT)
  ));
  const sentinelRef = useRef<HTMLDivElement>(null);
  const firstReadyFileRef = useRef<string | null>(null);
  const lastPageRef = useRef<HTMLDivElement>(null);
  const lastReadyRef = useRef(false);
  const reachedEndRef = useRef(false);
  const visiblePageCount = Math.min(numPages ?? 0, renderCount);
  const pageNumbers = Array.from({ length: visiblePageCount }, (_, index) => index + 1);

  const handleFirstPageReady = useCallback(() => {
    if (firstReadyFileRef.current === file) return;
    firstReadyFileRef.current = file;
    onFirstPageReady();
  }, [file, onFirstPageReady]);

  useEffect(() => {
    lastReadyRef.current = false;
    reachedEndRef.current = false;
  }, [file]);

  const checkReachedEnd = useCallback(() => {
    const root = scrollRootRef.current;
    const lastPage = lastPageRef.current;
    if (!root || !lastPage || !lastReadyRef.current || reachedEndRef.current) return;
    if (!isFinalPageVisible(lastPage.getBoundingClientRect(), root.getBoundingClientRect())) return;
    reachedEndRef.current = true;
    onReachedEnd();
  }, [onReachedEnd, scrollRootRef]);

  const handleLastPageReady = useCallback(() => {
    lastReadyRef.current = true;
    checkReachedEnd();
  }, [checkReachedEnd]);

  useEffect(() => {
    const root = scrollRootRef.current;
    if (!root) return;
    root.addEventListener("scroll", checkReachedEnd);
    return () => root.removeEventListener("scroll", checkReachedEnd);
  }, [checkReachedEnd, scrollRootRef]);

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
            inputRef={pageNumber === numPages ? lastPageRef : undefined}
            renderTextLayer={true}
            renderAnnotationLayer={false}
            onRenderSuccess={() => {
              if (pageNumber === 1) handleFirstPageReady();
              if (pageNumber === numPages) handleLastPageReady();
            }}
          />
        ))}
        {numPages !== null && renderCount < numPages && (
          <div ref={sentinelRef} aria-hidden="true" className="h-px w-full" />
        )}
      </Document>
    </>
  );
}
