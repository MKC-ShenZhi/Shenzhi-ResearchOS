"use client";

import { useRouter } from "next/navigation";
import type { KeyboardEvent, MouseEvent } from "react";

const INTERACTIVE_SELECTOR = [
  "a", "button", "input", "select", "textarea", "label", "summary", "dialog",
  '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="menu"]',
  '[contenteditable]:not([contenteditable="false"])',
  "[data-paper-card-interactive]",
].join(", ");

export const PAPER_CARD_INTERACTION_CLASS =
  "cursor-pointer outline-none ring-1 ring-transparent transition-[box-shadow] duration-200 hover:shadow-pop hover:ring-primary/20 focus-visible:ring-2 focus-visible:ring-primary/50 motion-reduce:transition-none";

export function usePaperCardNavigation(href: string, title: string, onNavigate?: () => void) {
  const router = useRouter();

  function isIndependentTarget(target: EventTarget, card: HTMLElement) {
    if (!(target instanceof Element) || !card.contains(target)) return true;
    const interactive = target.closest(INTERACTIVE_SELECTOR);
    return interactive !== null && interactive !== card;
  }

  function onClick(event: MouseEvent<HTMLElement>) {
    if (event.defaultPrevented || event.button !== 0 || event.altKey ||
        isIndependentTarget(event.target, event.currentTarget)) return;

    const selection = window.getSelection();
    if (selection && !selection.isCollapsed &&
        (event.currentTarget.contains(selection.anchorNode) ||
         event.currentTarget.contains(selection.focusNode))) return;

    if (event.metaKey || event.ctrlKey || event.shiftKey) {
      window.open(href, "_blank", "noopener,noreferrer");
    } else {
      onNavigate?.();
      router.push(href);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.defaultPrevented || event.repeat || event.target !== event.currentTarget ||
        (event.key !== "Enter" && event.key !== " ") ||
        event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    onNavigate?.();
    router.push(href);
  }

  return { onClick, onKeyDown, role: "link" as const, tabIndex: 0, "aria-label": title };
}
