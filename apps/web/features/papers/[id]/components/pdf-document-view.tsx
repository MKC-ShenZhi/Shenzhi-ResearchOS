"use client";

import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import {
  pdfTextRangeToRects,
  type HighlightColor,
  type PdfHighlight,
  type PdfHighlightRect,
} from "./pdf-text-range";
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export const HIGHLIGHT_BACKGROUND_COLORS: Record<HighlightColor, string> = {
  yellow: "rgb(250 204 21 / 0.16)",
  red: "rgb(248 113 113 / 0.14)",
  blue: "rgb(96 165 250 / 0.14)",
  green: "rgb(74 222 128 / 0.14)",
};

export function PdfDocumentView({
  file,
  width,
  numPages,
  onLoadSuccess,
  onLoadError,
  onPageRef,
  highlights,
  className,
}: {
  file: string;
  width: number;
  numPages: number | null;
  onLoadSuccess: (value: { numPages: number }) => void;
  onLoadError: (error: Error) => void;
  onPageRef: (pageNumber: number, node: HTMLDivElement | null) => void;
  highlights: PdfHighlight[];
  className?: string;
}) {
  const pageNumbers = numPages ? Array.from({ length: numPages }, (_, index) => index + 1) : [];
  const pageElements = useRef(new Map<number, HTMLDivElement>());
  const [highlightRects, setHighlightRects] = useState<Record<string, PdfHighlightRect[]>>({});

  const recalculateHighlightRects = useCallback(() => {
    const nextRects: Record<string, PdfHighlightRect[]> = {};
    highlights.forEach((highlight) => {
      const page = pageElements.current.get(highlight.pageNumber);
      if (!page) return;

      const rects = pdfTextRangeToRects(page, highlight);
      if (rects.length > 0) nextRects[highlight.id] = rects;
    });
    setHighlightRects(nextRects);
  }, [highlights]);

  const handlePageRef = useCallback(
    (pageNumber: number, node: HTMLDivElement | null) => {
      if (node) {
        pageElements.current.set(pageNumber, node);
      } else {
        pageElements.current.delete(pageNumber);
      }
      onPageRef(pageNumber, node);
    },
    [onPageRef],
  );

  useEffect(() => {
    recalculateHighlightRects();
  }, [recalculateHighlightRects]);

  useEffect(() => {
    const elements = Array.from(pageElements.current.values());
    if (elements.length === 0) return;

    const observer = new ResizeObserver(recalculateHighlightRects);
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [numPages, recalculateHighlightRects]);

  return (
    <>
      <style>{`
        .pdf-viewer-page {
          position: relative;
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
            inputRef={(node) => handlePageRef(pageNumber, node)}
            renderTextLayer={true}
            renderAnnotationLayer={false}
            onRenderTextLayerSuccess={recalculateHighlightRects}
          >
            {highlights
              .filter((highlight) => highlight.pageNumber === pageNumber)
              .map((highlight) => {
                const rects = highlightRects[highlight.id] ?? [];
                if (rects.length === 0) return null;

                return (
                  <div
                    key={highlight.id}
                    className="pointer-events-none absolute inset-0 z-0"
                    style={{ mixBlendMode: "multiply" }}
                    aria-hidden="true"
                  >
                    {rects.map((rect, index) => (
                      <span
                        key={`${highlight.id}-${index}`}
                        className="absolute rounded-sm"
                        style={{
                          left: `${rect.x * 100}%`,
                          top: `${rect.y * 100}%`,
                          width: `${rect.width * 100}%`,
                          height: `${rect.height * 100}%`,
                          backgroundColor: HIGHLIGHT_BACKGROUND_COLORS[highlight.color],
                        }}
                      />
                    ))}
                  </div>
                );
              })}
          </Page>
        ))}
      </Document>
    </>
  );
}
