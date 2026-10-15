"use client";

import { useEffect, type MouseEvent } from "react";
import { clearSearchScroll, readSearchScroll, saveSearchScroll } from "./search-scroll-state";

/** Only record navigation into Paper scope; ordinary searching must not replay old scroll. */
export function rememberSearchScroll(event: MouseEvent<HTMLElement>, returnTo: string): void {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.defaultPrevented) return;
  const link = (event.target as Element).closest<HTMLAnchorElement>("a[href]");
  if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
  const destination = new URL(link.href);
  if (destination.origin !== window.location.origin || !/^\/papers\/[^/]+(?:\/graph)?\/?$/.test(destination.pathname)) return;
  try {
    saveSearchScroll(window.sessionStorage, returnTo, window.scrollY);
  } catch {
    // Accessing sessionStorage itself can throw in restricted browser contexts.
  }
}

export function discardSearchScroll(returnTo: string): void {
  try {
    clearSearchScroll(window.sessionStorage, returnTo);
  } catch {
    // Storage is optional.
  }
}

export function useSearchScrollRestoration(returnTo: string, ready: boolean): void {
  useEffect(() => {
    let top: number | null = null;
    try {
      top = readSearchScroll(window.sessionStorage, returnTo);
    } catch {
      return;
    }
    if (top === null) return;

    let frame = 0;
    const cancel = () => {
      window.cancelAnimationFrame(frame);
      discardSearchScroll(returnTo);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", " "].includes(event.key)) cancel();
    };
    window.addEventListener("wheel", cancel, { passive: true });
    window.addEventListener("touchmove", cancel, { passive: true });
    window.addEventListener("keydown", onKeyDown);
    if (ready) {
      // Wait for result layout and the router's own scroll handling, including a cold cache.
      frame = window.requestAnimationFrame(() => {
        frame = window.requestAnimationFrame(() => {
          try {
            // Search/filter/page changes can invalidate the record before these frames run.
            const currentTop = readSearchScroll(window.sessionStorage, returnTo);
            if (currentTop === null) return;
            window.scrollTo({ top: currentTop, behavior: "instant" });
            discardSearchScroll(returnTo);
          } catch {
            // Storage can become unavailable after the effect has started.
          }
        });
      });
    }
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("wheel", cancel);
      window.removeEventListener("touchmove", cancel);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [returnTo, ready]);
}
