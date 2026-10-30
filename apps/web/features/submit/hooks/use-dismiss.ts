"use client";

import { useEffect, type RefObject } from "react";

/** 弹出层的通用关闭方式：点击外部或按 Esc */
export function useDismiss(open: boolean, rootRef: RefObject<HTMLElement | null>, onDismiss: () => void) {
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onDismiss();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, rootRef, onDismiss]);
}
