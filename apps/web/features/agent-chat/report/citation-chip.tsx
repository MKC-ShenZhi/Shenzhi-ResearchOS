"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { ExternalLink } from "lucide-react";
import type { PaperRef } from "./paper-ref";

/** Only http(s) links are rendered as anchors; anything else is dropped. */
const SAFE_URL = /^https?:\/\//i;

/** Presentational paper detail (title / authors / year / venue / doi / abstract / full text). */
export function PaperDetail({ paper }: { paper: PaperRef }) {
  return (
    <div className="max-h-80 max-w-[560px] overflow-auto px-5 pb-3 pt-4">
      <h3 className="text-base font-semibold leading-snug">{paper.title}</h3>
      {paper.authors.length > 0 && (
        <p className="mt-1 text-sm text-muted">{paper.authors.join(", ")}</p>
      )}
      {(paper.year || paper.venue || paper.doi || (paper.url && SAFE_URL.test(paper.url))) && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {paper.year && <span className="rounded-md border border-line px-1.5 py-0.5 text-xs text-muted">{paper.year}</span>}
          {paper.venue && <span className="rounded-md border border-line px-1.5 py-0.5 text-xs text-muted">{paper.venue}</span>}
          {paper.doi && (
            <a
              href={`https://doi.org/${paper.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-line px-1.5 py-0.5 text-xs text-primary no-underline transition-colors hover:bg-primary-soft"
            >
              {paper.doi}
            </a>
          )}
          {paper.url && SAFE_URL.test(paper.url) && (
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-xs text-primary no-underline transition-colors hover:bg-primary-soft"
            >
              <ExternalLink className="size-3" /> 打开全文
            </a>
          )}
        </div>
      )}
      {paper.document_id && (
        <p className="mt-1 text-xs text-faint">{paper.document_id}</p>
      )}
      {paper.abstract && <p className="mt-2 text-sm leading-relaxed">{paper.abstract}</p>}
    </div>
  );
}

/**
 * Hand-written anchored popover, portal-rendered so it escapes the report
 * card's scroll container. Anchored below-left of `anchorEl`, repositioned on
 * scroll/resize while open, closed by outside pointer-down or Escape.
 * Deliberately local to this file: the app has no shared popover primitive and
 * this is the only consumer (only badge/button/card/input/tabs live in
 * components/ui).
 */
function PaperPopover({
  open,
  onClose,
  anchorEl,
  children,
}: {
  open: boolean;
  onClose: () => void;
  anchorEl: HTMLElement | null;
  children: React.ReactNode;
}) {
  // The measured anchor is stored WITH the coordinates: reopening on another
  // chip must not paint one frame at the previous chip's position, and closing
  // needs no state reset (stale layout is simply not used while `!open`).
  const [layout, setLayout] = React.useState<{ anchor: HTMLElement; top: number; left: number } | null>(null);

  React.useEffect(() => {
    if (!open || !anchorEl) return;
    const update = () => {
      const rect = anchorEl.getBoundingClientRect();
      // Fixed coordinates inside the portal; a few guard pixels below the
      // trigger keep the panel from covering its own chip (outside-click would
      // otherwise close it on the very first click). Clamp so a chip near the
      // right edge doesn't push the panel out of the viewport.
      setLayout({
        anchor: anchorEl,
        top: rect.bottom + 6,
        left: Math.min(rect.left, Math.max(8, window.innerWidth - 576)),
      });
    };
    update();
    // Capture phase: the report body scrolls in its own container, so the
    // scroll event never bubbles to window.
    window.addEventListener("scroll", update, { capture: true, passive: true });
    window.addEventListener("resize", update, { passive: true });
    return () => {
      window.removeEventListener("scroll", update, { capture: true });
      window.removeEventListener("resize", update);
    };
  }, [open, anchorEl]);

  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-slot='paper-popover']")) return;
      if (anchorEl?.contains(target)) return;
      onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose, anchorEl]);

  if (!open || !anchorEl || !layout || layout.anchor !== anchorEl) return null;
  return createPortal(
    <div
      data-slot="paper-popover"
      role="dialog"
      className="fixed z-50 max-w-[calc(100vw-16px)] rounded-xl border border-line bg-card shadow-pop"
      style={{ top: layout.top, left: layout.left }}
    >
      {children}
    </div>,
    document.body,
  );
}

/**
 * Inline citation superscript. Rendered by the markdown bridge for every
 * `<Paper ns="..."></Paper>` tag; `ns` is a comma-separated list of 1-based
 * global paper numbers. Clicking opens a popover with the referenced paper(s).
 */
export function CitationChip({ ns, references }: { ns: string; references: PaperRef[] }) {
  const [anchorEl, setAnchorEl] = React.useState<HTMLElement | null>(null);

  const nums = ns
    .split(",")
    .map((s) => parseInt(s, 10))
    .filter((n) => Number.isFinite(n) && n >= 1 && n <= references.length);
  const papers = nums.map((n) => references[n - 1]).filter(Boolean) as PaperRef[];

  // Dangling citation (out of range): render literally rather than crash.
  if (papers.length === 0) {
    return <span>{`[${ns}]`}</span>;
  }

  return (
    <>
      <sup
        role="button"
        tabIndex={0}
        aria-label={`查看引用 ${nums.join(",")}`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setAnchorEl(e.currentTarget);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setAnchorEl(e.currentTarget);
          }
        }}
        className="inline cursor-pointer select-none align-super text-[0.72rem] font-semibold leading-none text-primary outline-none hover:underline focus-visible:rounded focus-visible:outline-2 focus-visible:outline-primary"
      >
        [{nums.join(",")}]
      </sup>
      <PaperPopover open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)} anchorEl={anchorEl}>
        {papers.map((p, i) => (
          <React.Fragment key={p.document_id}>
            {/* 文献之间用间距自然分隔（无分割线） */}
            <div className={i > 0 ? "mt-3" : undefined}>
              <PaperDetail paper={p} />
            </div>
          </React.Fragment>
        ))}
      </PaperPopover>
    </>
  );
}
