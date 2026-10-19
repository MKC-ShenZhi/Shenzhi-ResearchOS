"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import { useThemeStore } from "@/stores/theme";
import { cn } from "@/lib/utils";

/**
 * 日/夜模式切换(移动端顶栏)—— 点击在日间/夜间间显式切换,
 * 桌面端主题入口在侧边栏「设置」选项栏底部(日/夜/跟随系统)
 */
export function ThemeToggle({ className }: { className?: string }) {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );

  const dark =
    mounted &&
    (mode === "dark" ||
      (mode === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches));

  return (
    <button
      type="button"
      onClick={() => setMode(dark ? "light" : "dark")}
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
