"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import { useThemeStore } from "@/stores/theme";
import { isDarkThemePreset, supportsThemeMode } from "@/lib/theme-presets";
import { cn } from "@/lib/utils";

function subscribeSystemTheme(onChange: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function getSystemDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * 日/夜模式切换(移动端顶栏)—— 点击在日间/夜间间显式切换,
 * 桌面端主题入口在侧边栏「设置」选项栏底部(日/夜/跟随系统)
 */
export function ThemeToggle({ className }: { className?: string }) {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  const preset = useThemeStore((s) => s.preset);
  const setPreset = useThemeStore((s) => s.setPreset);
  const customTheme = useThemeStore((s) => s.customTheme);
  const setCustomAppearance = useThemeStore((s) => s.setCustomAppearance);
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );

  const systemDark = useSyncExternalStore(subscribeSystemTheme, getSystemDark, () => false);

  const dark =
    mounted &&
    ((preset === "custom" && customTheme.appearance === "dark") ||
      isDarkThemePreset(preset) ||
      (supportsThemeMode(preset) &&
        (mode === "dark" ||
          (mode === "system" && systemDark))));

  const toggleAppearance = () => {
    if (supportsThemeMode(preset)) {
      setMode(dark ? "light" : "dark");
      return;
    }
    if (preset === "custom") {
      setCustomAppearance(dark ? "light" : "dark");
      return;
    }
    setPreset(isDarkThemePreset(preset) ? "apple-light" : "apple-dark");
  };

  return (
    <button
      type="button"
      onClick={toggleAppearance}
      aria-label={dark ? "切换到日间模式" : "切换到夜间模式"}
      title={dark ? "切换到日间模式" : "切换到夜间模式"}
      className={cn(
        "flex size-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-chip hover:text-ink",
        className,
      )}
    >
      {!mounted ? (
        <span className="size-4" />
      ) : dark ? (
        <Sun className="size-4" strokeWidth={1.8} />
      ) : (
        <Moon className="size-4" strokeWidth={1.8} />
      )}
    </button>
  );
}
