"use client";

import { Suspense, useEffect, useRef, type ReactNode } from "react";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";

function RouteDismiss({ onClose }: { onClose: () => void }) {
  const href = useCurrentInternalPath();
  const previous = useRef(href);
  useEffect(() => {
    if (previous.current !== href) onClose();
    previous.current = href;
  }, [href, onClose]);
  return null;
}

/** One navigation instance serves both layouts; only the mobile overlay is transient. */
export function MobileNavDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(panel.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]') ?? [])
      .filter((element) => element.getClientRects().length > 0);
    focusable()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); }
      if (event.key !== "Tab") return;
      const items = focusable();
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !panel.current?.contains(document.activeElement))) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !panel.current?.contains(document.activeElement))) {
        event.preventDefault(); first?.focus();
      }
    };
    const desktop = window.matchMedia("(min-width: 1024px)");
    const onDesktop = () => { if (desktop.matches) onClose(); };
    onDesktop();
    desktop.addEventListener("change", onDesktop);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      desktop.removeEventListener("change", onDesktop);
      document.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [open, onClose]);

  return (
    <div id="app-navigation" ref={panel} role={open ? "dialog" : undefined} aria-modal={open || undefined} aria-label="主导航" className={open ? "fixed inset-0 z-50 lg:contents" : "contents"}
      onClick={(event) => {
        const target = event.target as HTMLElement;
        // Same-route links also dismiss, while modified clicks retain native Link behavior.
        if (open && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && target.closest("a[href]")) onClose();
      }}>
      <Suspense fallback={null}><RouteDismiss onClose={onClose} /></Suspense>
      {open && <div aria-hidden="true" className="absolute inset-0 bg-black/40 lg:hidden" onClick={onClose} />}
      {children}
    </div>
  );
}
