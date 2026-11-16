"use client";

import { useEffect, type MouseEvent } from "react";
import { clearSearchScroll, readSearchScroll, saveSearchScroll } from "./search-scroll-state";

/** Record result activation only; changing search conditions must not replay old scroll. */
export function rememberSearchScroll(event: MouseEvent<HTMLElement>, returnTo: string, scope: string | null = "anonymous"): void {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.defaultPrevented) return;
  const link = (event.target as Element).closest<HTMLAnchorElement>("a[href]");
  if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
  const destination = new URL(link.href);
  const fromDirectory = new URL(returnTo, window.location.origin).pathname === "/knowledge/search/conferences";
  const opensConference = fromDirectory && destination.pathname === "/knowledge/search" && destination.searchParams.get("mode") === "conference";
  if (destination.origin !== window.location.origin || (!opensConference && !/^\/papers\/[^/]+(?:\/graph)?\/?$/.test(destination.pathname))) return;
  saveCurrentSearchScroll(returnTo, scope);
}

/** Called only when a paper card actually navigates in the current tab. */
export function saveCurrentSearchScroll(returnTo: string, scope: string | null): void {
  if (!scope) return;
  try {
    saveSearchScroll(window.sessionStorage, returnTo, window.scrollY, Date.now(), scope);
  } catch {
    // Accessing sessionStorage itself can throw in restricted browser contexts.
  }
}

export function discardSearchScroll(returnTo: string, scope: string | null = "anonymous"): void {
  if (!scope) return;
  try {
    clearSearchScroll(window.sessionStorage, returnTo, scope);
  } catch {
    // Storage is optional.
  }
}

export function useSearchScrollRestoration(returnTo: string, ready: boolean, scope: string | null = "anonymous"): void {
  useEffect(() => {
    if (!scope) return;
    let top: number | null = null;
    try {
      top = readSearchScroll(window.sessionStorage, returnTo, Date.now(), scope);
    } catch {
      return;
    }
    if (top === null) return;

    let frame = 0;
    const cancel = () => {
      window.cancelAnimationFrame(frame);
      discardSearchScroll(returnTo, scope);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.defaultPrevented && ["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", " "].includes(event.key)) cancel();
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
            const currentTop = readSearchScroll(window.sessionStorage, returnTo, Date.now(), scope);
            if (currentTop === null) return;
            window.scrollTo({ top: currentTop, behavior: "instant" });
            discardSearchScroll(returnTo, scope);
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
  }, [returnTo, ready, scope]);
}
