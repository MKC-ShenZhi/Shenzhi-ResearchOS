"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { advanceHoverIntent, startHoverIntent, type HoverIntent } from "./settings-menu-hover";

export function useSettingsMenuHover(disabled: boolean) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLAnchorElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intent = useRef<HoverIntent | null>(null);
  const pointerInside = useRef(false);
  const hasKeyboardFocus = useCallback(() => {
    return rootRef.current?.contains(document.activeElement) && document.activeElement?.matches(":focus-visible");
  }, []);

  const cancelClose = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    intent.current = null;
  }, []);
  const close = useCallback(() => {
    cancelClose();
    setOpen(false);
  }, [cancelClose]);
  const show = () => {
    if (disabled) return;
    cancelClose();
    setOpen(true);
  };
  const scheduleClose = () => {
    if (timer.current !== null) return;
    const check = () => {
      timer.current = null;
      if (hasKeyboardFocus()) return;
      const rect = menuRef.current?.getBoundingClientRect();
      const next = intent.current && rect
        ? advanceHoverIntent(intent.current, intent.current.point, rect, Date.now())
        : null;
      intent.current = next;
      if (next) timer.current = setTimeout(check, 100);
      else close();
    };
    timer.current = setTimeout(check, 300);
  };

  useEffect(() => {
    if (!open || disabled) return;
    const onMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      if (rootRef.current?.contains(event.target as Node)) return;
      if (hasKeyboardFocus()) return;
      const rect = menuRef.current?.getBoundingClientRect();
      if (intent.current && rect) {
        intent.current = advanceHoverIntent(intent.current, { x: event.clientX, y: event.clientY }, rect, Date.now());
        // A diagonal route crosses the navigation above Settings. Those links
        // are still clickable, but merely crossing them must not cancel intent.
        if (intent.current) return;
        close();
        return;
      }
      if (event.target instanceof Element && event.target.closest("a, button, [role='button'], [role='tab']")) {
        close();
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (rootRef.current?.contains(document.activeElement)) triggerRef.current?.focus();
      close();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    window.addEventListener("blur", close);
    return () => {
      cancelClose();
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
      window.removeEventListener("blur", close);
    };
  }, [open, disabled, cancelClose, close, hasKeyboardFocus]);

  return {
    open: open && !disabled,
    rootRef,
    triggerRef,
    menuRef,
    close,
    onPointerEnter: (event: ReactPointerEvent) => {
      if (event.pointerType === "touch") return;
      pointerInside.current = true;
      show();
    },
    onPointerLeave: (event: ReactPointerEvent) => {
      if (event.pointerType === "touch" || disabled || !open) return;
      pointerInside.current = false;
      const now = Date.now();
      const point = { x: event.clientX, y: event.clientY };
      const next = startHoverIntent(point, now);
      const rect = menuRef.current?.getBoundingClientRect();
      intent.current = rect ? advanceHoverIntent(next, point, rect, now) : next;
      scheduleClose();
    },
    onFocus: show,
    onBlur: (event: React.FocusEvent) => {
      if (!open || disabled) return;
      if (rootRef.current?.contains(event.relatedTarget as Node)) return;
      if (!pointerInside.current) scheduleClose();
    },
  };
}
