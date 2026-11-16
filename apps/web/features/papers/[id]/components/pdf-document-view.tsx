"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
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

type ScrollAnchor = { frame: HTMLElement; fractionX: number; fractionY: number };

/** 视口中心所在的页面及其相对位置，缩放后据此恢复滚动位置。 */
function readScrollAnchor(root: HTMLElement): ScrollAnchor | null {
  const rootRect = root.getBoundingClientRect();
  const centerX = rootRect.left + root.clientWidth / 2;
  const centerY = rootRect.top + root.clientHeight / 2;
  const frames = root.querySelectorAll<HTMLElement>("[data-pdf-frame]");
  for (const frame of frames) {
    const rect = frame.getBoundingClientRect();
    if (rect.bottom < centerY) continue;
    return {
      frame,
      fractionX: rect.width ? (centerX - rect.left) / rect.width : 0.5,
      fractionY: rect.height ? Math.max(0, (centerY - rect.top) / rect.height) : 0,
    };
  }
  return null;
}

/**
 * react-pdf 在缩放变化时会以新的 key 重新挂载画布，新画布在渲染完成前为空白。
 * 页面框按页面比例固定尺寸，避免布局塌陷；宽度变化时把旧画布内容复制到覆盖层上，
 * 拉伸显示直到新画布渲染完成，使缩放过程保持连续。
 */
function PdfPageFrame({
  pageNumber,
  width,
  scrollRootRef,
  inputRef,
  onRenderSuccess,
}: {
  pageNumber: number;
  width: number;
  scrollRootRef: RefObject<HTMLElement | null>;
  inputRef?: RefObject<HTMLDivElement | null>;
  onRenderSuccess: () => void;
}) {
  const [aspectRatio, setAspectRatio] = useState<number | null>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const snapshotRef = useRef<HTMLCanvasElement>(null);
  const liveCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const renderedCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const renderedWidthRef = useRef<number | null>(null);

  // 布局副作用先于 react-pdf 清理旧画布的副作用执行，此时旧画布的像素仍然完整。
  useLayoutEffect(() => {
    const snapshot = snapshotRef.current;
    const source = renderedCanvasRef.current;
    const frame = frameRef.current;
    const root = scrollRootRef.current;
    if (!snapshot || !source || !frame || !root) return;
    if (renderedWidthRef.current === null || renderedWidthRef.current === width) return;
    if (!snapshot.hidden || source.width === 0 || source.height === 0) return;

    // 只为视口附近的页面保留快照，避免长论文缩放时复制所有页面。
    const rootRect = root.getBoundingClientRect();
    const rect = frame.getBoundingClientRect();
    if (rect.bottom < rootRect.top - root.clientHeight || rect.top > rootRect.bottom + root.clientHeight) return;

    snapshot.width = source.width;
    snapshot.height = source.height;
    snapshot.getContext("2d")?.drawImage(source, 0, 0);
    snapshot.hidden = false;
  }, [scrollRootRef, width]);

  const handleRenderSuccess = () => {
    renderedCanvasRef.current = liveCanvasRef.current;
    renderedWidthRef.current = width;
    const snapshot = snapshotRef.current;
    if (snapshot && !snapshot.hidden) {
      snapshot.hidden = true;
      // 释放快照占用的位图内存。
      snapshot.width = 0;
      snapshot.height = 0;
    }
    onRenderSuccess();
  };

  return (
    <div
      ref={frameRef}
      data-pdf-frame
      className="pdf-viewer-frame"
      style={aspectRatio ? { width, height: Math.floor(width * aspectRatio) } : undefined}
    >
      <Page
        pageNumber={pageNumber}
        width={width}
        className="pdf-viewer-page isolate"
        inputRef={inputRef}
        canvasRef={(canvas) => {
          if (canvas) liveCanvasRef.current = canvas;
        }}
        renderTextLayer={true}
        renderAnnotationLayer={false}
        onLoadSuccess={(page) => {
          if (page.width > 0) setAspectRatio(page.height / page.width);
        }}
        onRenderSuccess={handleRenderSuccess}
      />
      <canvas ref={snapshotRef} hidden aria-hidden="true" className="pdf-viewer-snapshot" />
    </div>
  );
}

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
  const scrollAnchorRef = useRef<ScrollAnchor | null>(null);
  const visiblePageCount = Math.min(numPages ?? 0, renderCount);
  const pageNumbers = Array.from({ length: visiblePageCount }, (_, index) => index + 1);

  const handleFirstPageReady = useCallback(() => {
    if (firstReadyFileRef.current === file) return;
    firstReadyFileRef.current = file;
    const root = scrollRootRef.current;
    if (root) scrollAnchorRef.current = readScrollAnchor(root);
    onFirstPageReady();
  }, [file, onFirstPageReady, scrollRootRef]);

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
    const root = scrollRootRef.current;
    if (!root) return;
    let frame = 0;
    const recordAnchor = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        scrollAnchorRef.current = readScrollAnchor(root);
      });
    };
    root.addEventListener("scroll", recordAnchor, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      root.removeEventListener("scroll", recordAnchor);
    };
  }, [scrollRootRef]);

  // 宽度变化后把缩放前视口中心的位置重新对准视口中心。
  useLayoutEffect(() => {
    const root = scrollRootRef.current;
    const anchor = scrollAnchorRef.current;
    if (!root || !anchor?.frame.isConnected) return;
    const rootRect = root.getBoundingClientRect();
    const rect = anchor.frame.getBoundingClientRect();
    root.scrollTop += rect.top + anchor.fractionY * rect.height - (rootRect.top + root.clientHeight / 2);
    root.scrollLeft += rect.left + anchor.fractionX * rect.width - (rootRect.left + root.clientWidth / 2);
  }, [scrollRootRef, width]);

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
        .pdf-viewer-frame {
          position: relative;
          flex: none;
          overflow: hidden;
          background: #fff;
          border-radius: 2px;
          box-shadow: 0 0 0 1px rgb(0 0 0 / 0.04), var(--shadow-pop);
        }

        .pdf-viewer-page {
          position: relative;
        }

        .pdf-viewer-snapshot {
          position: absolute;
          inset: 0;
          z-index: 2;
          width: 100%;
          height: 100%;
          pointer-events: none;
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
          <PdfPageFrame
            key={pageNumber}
            pageNumber={pageNumber}
            width={width}
            scrollRootRef={scrollRootRef}
            inputRef={pageNumber === numPages ? lastPageRef : undefined}
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
