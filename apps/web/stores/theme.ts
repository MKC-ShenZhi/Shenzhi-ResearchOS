"use client";

import { create } from "zustand";
import type { ThemeMode } from "@/clients/settings/types";
import {
  createCustomThemeVariables,
  CUSTOM_THEME_STORAGE_KEY,
  CUSTOM_THEME_VARIABLES,
  CUSTOM_THEME_VARS_STORAGE_KEY,
  DEFAULT_CUSTOM_THEME,
  normalizeCustomThemeConfig,
  type CustomThemeAppearance,
  type CustomThemeConfig,
} from "@/lib/custom-theme";
import { isDarkThemePreset, isThemePreset, supportsThemeMode, type ThemePreset } from "@/lib/theme-presets";

export type { ThemeMode } from "@/clients/settings/types";

const STORAGE_KEY = "shenzhi-theme";
const PRESET_STORAGE_KEY = "shenzhi-theme-preset";

function prefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyCustomVariables(config: CustomThemeConfig | null) {
  for (const property of CUSTOM_THEME_VARIABLES) {
    document.documentElement.style.removeProperty(property);
  }
  if (!config) return;
  const variables = createCustomThemeVariables(config);
  for (const [property, value] of Object.entries(variables)) {
    document.documentElement.style.setProperty(property, value);
  }
}

function apply(mode: ThemeMode, preset: ThemePreset, customTheme: CustomThemeConfig) {
  const dark =
    isDarkThemePreset(preset) ||
    (preset === "custom" && customTheme.appearance === "dark") ||
    (supportsThemeMode(preset) &&
      (mode === "dark" || (mode === "system" && prefersDark())));
  applyCustomVariables(preset === "custom" ? customTheme : null);
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

function readStoredCustomTheme(): CustomThemeConfig {
  if (typeof window === "undefined") return DEFAULT_CUSTOM_THEME;
  try {
    const stored = localStorage.getItem(CUSTOM_THEME_STORAGE_KEY);
    return normalizeCustomThemeConfig(stored ? JSON.parse(stored) : null);
  } catch {
    return DEFAULT_CUSTOM_THEME;
  }
}

function persistCustomTheme(config: CustomThemeConfig) {
  try {
    localStorage.setItem(CUSTOM_THEME_STORAGE_KEY, JSON.stringify(config));
    localStorage.setItem(CUSTOM_THEME_VARS_STORAGE_KEY, JSON.stringify(createCustomThemeVariables(config)));
  } catch {
    /* 隐私模式下忽略 */
  }
}

interface ThemeState {
  mode: ThemeMode;
  preset: ThemePreset;
  customTheme: CustomThemeConfig;
  setMode: (mode: ThemeMode) => void;
  setPreset: (preset: ThemePreset) => void;
  setCustomAccent: (accent: string) => void;
  setCustomAppearance: (appearance: CustomThemeAppearance) => void;
  resetCustomTheme: () => void;
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
  customTheme: DEFAULT_CUSTOM_THEME,
  setMode: (mode) => {
    set({ mode });
    const { preset, customTheme } = useThemeStore.getState();
    apply(mode, preset, customTheme);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* 隐私模式下忽略 */
    }
  },
  setPreset: (preset) => {
    set({ preset });
    const { mode, customTheme } = useThemeStore.getState();
    apply(mode, preset, customTheme);
    if (preset === "custom") {
      persistCustomTheme(customTheme);
    }
    try {
      localStorage.setItem(PRESET_STORAGE_KEY, preset);
    } catch {
      /* 隐私模式下忽略 */
    }
  },
  setCustomAccent: (accent) => {
    const customTheme = normalizeCustomThemeConfig({
      ...useThemeStore.getState().customTheme,
      accent,
    });
    set({ customTheme, preset: "custom" });
    apply(useThemeStore.getState().mode, "custom", customTheme);
    persistCustomTheme(customTheme);
    try {
      localStorage.setItem(PRESET_STORAGE_KEY, "custom");
    } catch {
      /* 隐私模式下忽略 */
    }
  },
  setCustomAppearance: (appearance) => {
    const customTheme = normalizeCustomThemeConfig({
      ...useThemeStore.getState().customTheme,
      appearance,
    });
    set({ customTheme, preset: "custom" });
    apply(useThemeStore.getState().mode, "custom", customTheme);
    persistCustomTheme(customTheme);
    try {
      localStorage.setItem(PRESET_STORAGE_KEY, "custom");
    } catch {
      /* 隐私模式下忽略 */
    }
  },
  resetCustomTheme: () => {
    const customTheme = DEFAULT_CUSTOM_THEME;
    set({ customTheme, preset: "custom" });
    apply(useThemeStore.getState().mode, "custom", customTheme);
    persistCustomTheme(customTheme);
  },
}));

/** 首帧 hydration 完成后再对齐浏览器持久化偏好（layout 内联脚本已处理 DOM class）。 */
export function hydrateThemeStoreFromStorage() {
  if (typeof window === "undefined") return;
  const stored = readStored();
  const preset = readStoredPreset();
  const customTheme = readStoredCustomTheme();
  useThemeStore.setState({ mode: stored, preset, customTheme });
  apply(stored, preset, customTheme);
}

// 跟随系统模式:系统主题变化时实时重算
if (typeof window !== "undefined") {
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      const { mode, preset } = useThemeStore.getState();
      if (mode === "system" && supportsThemeMode(preset)) {
        apply(mode, preset, useThemeStore.getState().customTheme);
      }
    });
}
