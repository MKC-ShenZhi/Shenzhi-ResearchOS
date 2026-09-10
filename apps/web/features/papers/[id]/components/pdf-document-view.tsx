"use client";

import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import { cn } from "@/lib/utils";
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export function PdfDocumentView({
  file,
  width,
  numPages,
  onLoadSuccess,
  onLoadError,
  className,
}: {
  file: string;
  width: number;
  numPages: number | null;
  onLoadSuccess: (value: { numPages: number }) => void;
  onLoadError: (error: Error) => void;
  className?: string;
}) {
  const pageNumbers = numPages ? Array.from({ length: numPages }, (_, index) => index + 1) : [];

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
            renderTextLayer={true}
            renderAnnotationLayer={false}
          />
        ))}
      </Document>
    </>
  );
}
