"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";

export interface QuoteDraft { text: string; messageId: string }
type Candidate = QuoteDraft & { left: number; top: number };

/** Selection is only a preview; committing a quote always requires a button click. */
export function SelectionQuoteAction({ containerRef, onQuote }: {
  containerRef: RefObject<HTMLDivElement | null>;
  onQuote: (quote: QuoteDraft) => void;
}) {
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let frame = 0;
    const hide = () => {
      cancelAnimationFrame(frame);
      setCandidate(null);
    };
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        // Tabbing to the action must preserve the captured selection.
        if (document.activeElement === buttonRef.current) return;
        const selection = window.getSelection();
        const text = selection?.toString().trim() ?? "";
        const container = containerRef.current;
        if (!container || !selection || selection.isCollapsed || selection.rangeCount !== 1 || !text) {
          setCandidate(null);
          return;
        }
        const range = selection.getRangeAt(0);
        const element = (node: Node) => node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
        const start = element(range.startContainer);
        const end = element(range.endContainer);
        const source = start?.closest<HTMLElement>("[data-quote-source]");
        const excluded = 'input, textarea, select, button, [contenteditable]:not([contenteditable="false"]), [role="textbox"]';
        const active = document.activeElement;
        if (!source || !container.contains(source) || end?.closest("[data-quote-source]") !== source
          || start?.closest(excluded) || end?.closest(excluded) || active?.matches(excluded)
          || Array.from(source.querySelectorAll(excluded)).some((node) => range.intersectsNode(node))) {
          setCandidate(null);
          return;
        }
        const rect = range.getBoundingClientRect();
        const bounds = container.getBoundingClientRect();
        if (!rect.width || !rect.height || rect.bottom < Math.max(0, bounds.top)
          || rect.top > Math.min(window.innerHeight, bounds.bottom)) {
          setCandidate(null);
          return;
        }
        // Fixed 132 × 36 action, with an 8px viewport gutter.
        const left = Math.max(8, Math.min(rect.left, window.innerWidth - 140));
        const top = Math.max(8, Math.min(rect.top >= 52 ? rect.top - 44 : rect.bottom + 8, window.innerHeight - 44));
        const next = { text, messageId: source.dataset.quoteSource!, left, top };
        setCandidate((previous) => previous?.text === text && previous.messageId === next.messageId
          && previous.left === left && previous.top === top ? previous : next);
      });
    };
    const outside = (event: PointerEvent) => {
      if (!buttonRef.current?.contains(event.target as Node)) hide();
    };
    const keydown = (event: KeyboardEvent) => { if (event.key === "Escape") hide(); };
    document.addEventListener("selectionchange", update);
    document.addEventListener("pointerup", update);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keydown);
    document.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    window.addEventListener("blur", hide);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("selectionchange", update);
      document.removeEventListener("pointerup", update);
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keydown);
      document.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
      window.removeEventListener("blur", hide);
    };
  }, [containerRef]);

  return candidate && createPortal(
    <button ref={buttonRef} type="button"
      className="fixed z-50 h-9 w-[132px] max-w-[calc(100vw-16px)] cursor-pointer rounded-lg border border-line bg-card text-xs font-medium text-ink shadow-lg hover:bg-primary-soft focus-visible:outline-2 focus-visible:outline-primary"
      style={{ left: candidate.left, top: candidate.top }}
      onPointerDown={(event) => event.preventDefault()}
      onClick={() => {
        onQuote({ text: candidate.text, messageId: candidate.messageId });
        setCandidate(null);
        window.getSelection()?.removeAllRanges();
        containerRef.current?.parentElement?.querySelector<HTMLTextAreaElement>("textarea")?.focus({ preventScroll: true });
      }}>
      询问深知AI
    </button>, document.body,
  );
}
