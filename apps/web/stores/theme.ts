"use client";

import { create } from "zustand";
import type { ThemeMode } from "@/clients/settings";

export type { ThemeMode } from "@/clients/settings";

const STORAGE_KEY = "shenzhi-theme";

function prefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function apply(mode: ThemeMode) {
  const dark = mode === "dark" || (mode === "system" && prefersDark());
  document.documentElement.classList.toggle("dark", dark);
}

function readStored(): ThemeMode {
  if (typeof window === "undefined") return "system";
  const t = localStorage.getItem(STORAGE_KEY);
  return t === "light" || t === "dark" || t === "system" ? t : "system";
}

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

/**
 * 主题模式(日间/夜间/跟随系统)—— 与 layout.tsx 内联脚本共用 localStorage 键,
 * 脚本负责首屏前定主题避免闪烁,这里负责切换、持久化与系统主题变化跟随
 */
export const useThemeStore = create<ThemeState>()((set) => ({
  mode: readStored(),
  setMode: (mode) => {
    set({ mode });
    apply(mode);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* 隐私模式下忽略 */
    }
  },
}));

// 跟随系统模式:系统主题变化时实时重算
if (typeof window !== "undefined") {
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (useThemeStore.getState().mode === "system") apply("system");
    });
}
