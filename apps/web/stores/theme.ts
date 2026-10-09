"use client";

import { create } from "zustand";
import type { ThemeMode } from "@/clients/settings/types";
import { isThemePreset, type ThemePreset } from "@/lib/theme-presets";

export type { ThemeMode } from "@/clients/settings/types";

const STORAGE_KEY = "shenzhi-theme";
const PRESET_STORAGE_KEY = "shenzhi-theme-preset";

function prefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function apply(mode: ThemeMode, preset: ThemePreset) {
  const dark =
    preset === "apple-dark" ||
    (preset === "shenzhi" &&
      (mode === "dark" || (mode === "system" && prefersDark())));
  document.documentElement.dataset.theme = preset;
  document.documentElement.classList.toggle("dark", dark);
}

function readStored(): ThemeMode {
  if (typeof window === "undefined") return "system";
  const queryTheme = new URLSearchParams(window.location.search).get("theme");
  if (queryTheme === "light" || queryTheme === "dark" || queryTheme === "system") {
    return queryTheme;
  }
  const t = localStorage.getItem(STORAGE_KEY);
  return t === "light" || t === "dark" || t === "system" ? t : "system";
}

function readStoredPreset(): ThemePreset {
  if (typeof window === "undefined") return "shenzhi";
  const queryTheme = new URLSearchParams(window.location.search).get("theme");
  if (queryTheme === "light" || queryTheme === "dark" || queryTheme === "system") {
    return "shenzhi";
  }
  if (isThemePreset(queryTheme)) return queryTheme;
  const preset = localStorage.getItem(PRESET_STORAGE_KEY);
  return isThemePreset(preset) ? preset : "shenzhi";
}

interface ThemeState {
  mode: ThemeMode;
  preset: ThemePreset;
  setMode: (mode: ThemeMode) => void;
  setPreset: (preset: ThemePreset) => void;
}

/**
 * 主题模式(日间/夜间/跟随系统)—— 与 layout.tsx 内联脚本共用 localStorage 键,
 * 脚本负责首屏前定主题避免闪烁,这里负责切换、持久化与系统主题变化跟随
 */
/** SSR 与 hydration 首帧必须使用固定默认值，避免 localStorage 造成 mismatch。 */
const SSR_THEME_DEFAULT: ThemeMode = "system";

export const useThemeStore = create<ThemeState>()((set) => ({
  mode: SSR_THEME_DEFAULT,
  preset: "shenzhi",
  setMode: (mode) => {
    set({ mode });
    apply(mode, useThemeStore.getState().preset);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* 隐私模式下忽略 */
    }
  },
  setPreset: (preset) => {
    set({ preset });
    apply(useThemeStore.getState().mode, preset);
    try {
      localStorage.setItem(PRESET_STORAGE_KEY, preset);
    } catch {
      /* 隐私模式下忽略 */
    }
  },
}));

/** 首帧 hydration 完成后再对齐浏览器持久化偏好（layout 内联脚本已处理 DOM class）。 */
export function hydrateThemeStoreFromStorage() {
  if (typeof window === "undefined") return;
  const stored = readStored();
  const preset = readStoredPreset();
  useThemeStore.setState({ mode: stored, preset });
  apply(stored, preset);
}

// 跟随系统模式:系统主题变化时实时重算
if (typeof window !== "undefined") {
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      const { mode, preset } = useThemeStore.getState();
      if (mode === "system" && preset === "shenzhi") apply(mode, preset);
    });
}
