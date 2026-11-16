"use client";

import Image from "next/image";
import { LoaderCircle, RotateCcw, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface PaperImagePreviewProps {
  src: string;
  previewSrc: string | null;
  title: string;
  onClose: () => void;
}

export function PaperImagePreview({ src, previewSrc, title, onClose }: PaperImagePreviewProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  function close() {
    dialogRef.current?.close();
    onClose();
  }

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); close(); }}
      onClick={(event) => { if (event.target === event.currentTarget) close(); }}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
        const first = buttons[0];
        const last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none border-0 bg-transparent p-4 text-ink backdrop:bg-black/65 open:flex open:items-center open:justify-center sm:p-8"
    >
      <div className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-card shadow-pop">
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-4 py-3">
          <h2 id={titleId} className="min-w-0 truncate text-sm font-medium">{title} · 原图</h2>
          <button
            type="button"
            autoFocus
            aria-label="关闭图片预览"
            onClick={close}
            className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted hover:bg-chip hover:text-ink focus-visible:outline-2 focus-visible:outline-primary"
          >
            <X className="size-5" />
          </button>
        </div>
        <div className="relative h-[75dvh] min-h-0 bg-chip" aria-busy={!loaded && !failed}>
          {previewSrc && !loaded && (
            <Image src={previewSrc} alt="" fill unoptimized className="object-contain" />
          )}
          {!failed && (
            <Image
              key={attempt}
              src={src}
              alt={`${title} 的论文原图`}
              fill
              unoptimized
              loading="eager"
              className={`object-contain ${loaded ? "opacity-100" : "opacity-0"}`}
              onLoad={() => setLoaded(true)}
              onError={() => setFailed(true)}
            />
          )}
          {!loaded && (
            <div className="absolute inset-x-0 bottom-4 flex justify-center px-4">
              <div role="status" className="flex items-center gap-2 rounded-lg bg-card/95 px-3 py-2 text-xs text-muted shadow-card">
                {failed ? (
                  <>
                    <span>原图加载失败</span>
                    <button
                      type="button"
                      onClick={() => { setFailed(false); setAttempt((value) => value + 1); }}
                      className="inline-flex cursor-pointer items-center gap-1 rounded px-1 py-0.5 text-primary hover:underline focus-visible:outline-2 focus-visible:outline-primary"
                    >
                      <RotateCcw className="size-3.5" />重试
                    </button>
                  </>
                ) : (
                  <><LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" />正在加载原图…</>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </dialog>,
    document.body,
  );
}
