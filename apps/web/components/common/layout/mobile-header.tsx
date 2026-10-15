"use client";

import { Menu } from "lucide-react";
import { Logo } from "./logo";
import { ThemeToggle } from "./theme-toggle";

export function MobileHeader({ open, onOpen }: { open: boolean; onOpen: () => void }) {
  return (
    <header className="sticky top-0 z-20 flex h-[calc(3.5rem+env(safe-area-inset-top))] items-center gap-3 border-b border-line bg-card px-4 pt-[env(safe-area-inset-top)] lg:hidden">
      <button type="button" onClick={onOpen} aria-label="打开导航" aria-expanded={open} aria-controls="app-navigation" className="flex size-10 items-center justify-center rounded-lg text-ink hover:bg-chip">
        <Menu className="size-5" />
      </button>
      <Logo />
      <ThemeToggle className="ml-auto" />
    </header>
  );
}
