"use client";

import { useLayoutEffect, useRef, useState } from "react";

/** Measure data-driven changes and wrapping without moving the caret or focus. */
export function useComposerTextarea(value: string, expanded: boolean, isHome: boolean) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [overflowing, setOverflowing] = useState(false);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const resize = () => {
      const previousScroll = textarea.scrollTop;
      textarea.style.height = "0px";
      const styles = getComputedStyle(textarea);
      const minimum = parseFloat(styles.minHeight);
      const viewport = window.visualViewport;
      const viewportLimit = viewport && viewport.scale === 1
        ? viewport.height * (expanded ? 0.5 : isHome ? 0.24 : 0.3)
        : Infinity;
      const maximum = Math.max(minimum, Math.min(parseFloat(styles.maxHeight), viewportLimit));
      const contentHeight = textarea.scrollHeight;
      const height = Math.min(maximum, Math.max(minimum, contentHeight));
      textarea.style.height = `${height}px`;
      textarea.style.overflowY = contentHeight > height + 1 ? "auto" : "hidden";
      textarea.scrollTop = previousScroll;
      setOverflowing(contentHeight > height + 1);
    };
    resize();
    let width = textarea.clientWidth;
    const observer = new ResizeObserver(() => {
      if (textarea.clientWidth === width) return;
      width = textarea.clientWidth;
      resize();
    });
    observer.observe(textarea);
    window.addEventListener("resize", resize);
    window.visualViewport?.addEventListener("resize", resize);
    // Font loading can change wrapping after the initial measurement.
    document.fonts.addEventListener("loadingdone", resize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", resize);
      window.visualViewport?.removeEventListener("resize", resize);
      document.fonts.removeEventListener("loadingdone", resize);
    };
  }, [value, expanded, isHome]);

  return { textareaRef, overflowing };
}
