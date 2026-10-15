"use client";

import { useEffect, useRef } from "react";

/** Mobile keyboard resizing belongs to layout, never to business state. */
export function useVisualViewport<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const viewport = window.visualViewport;
    const element = ref.current;
    if (!viewport || !element) return;
    const update = () => {
      // Pinch zoom should not resize the workspace and reflow the reader.
      if (viewport.scale === 1) element.style.setProperty("--visual-viewport-height", `${viewport.height}px`);
    };
    update();
    viewport.addEventListener("resize", update);
    return () => viewport.removeEventListener("resize", update);
  }, []);
  return ref;
}
