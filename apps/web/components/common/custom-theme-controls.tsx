"use client";

import { Moon, RotateCcw, Sun } from "lucide-react";
import { CUSTOM_THEME_SWATCHES } from "@/lib/custom-theme";
import { cn } from "@/lib/utils";
import { useThemeStore } from "@/stores/theme";

export function CustomThemeControls({ compact = false }: { compact?: boolean }) {
  const customTheme = useThemeStore((state) => state.customTheme);
  const setCustomAccent = useThemeStore((state) => state.setCustomAccent);
  const setCustomAppearance = useThemeStore((state) => state.setCustomAppearance);
  const resetCustomTheme = useThemeStore((state) => state.resetCustomTheme);

  return (
    <div className={cn("rounded-xl border border-line bg-chip", compact ? "p-2" : "p-4")}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className={cn("font-medium text-ink", compact ? "text-xs" : "text-sm")}>自定义调色板</p>
          <p className={cn("text-muted", compact ? "text-[10px]" : "mt-0.5 text-xs")}>{customTheme.accent}</p>
        </div>
        <div className="flex items-center gap-1">
          {(["light", "dark"] as const).map((appearance) => {
            const Icon = appearance === "light" ? Sun : Moon;
            const label = appearance === "light" ? "浅色" : "深色";
            return (
              <button
                key={appearance}
                type="button"
                title={`${label}自定义主题`}
                aria-label={`${label}自定义主题`}
                aria-pressed={customTheme.appearance === appearance}
                onClick={() => setCustomAppearance(appearance)}
                className={cn(
                  "flex items-center justify-center rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                  compact ? "size-7" : "size-9",
                  customTheme.appearance === appearance
                    ? "bg-primary-soft text-primary"
                    : "text-muted hover:bg-card hover:text-ink",
                )}
              >
                <Icon className={compact ? "size-3.5" : "size-4"} strokeWidth={1.8} />
              </button>
            );
          })}
          <button
            type="button"
            title="恢复默认自定义配色"
            aria-label="恢复默认自定义配色"
            onClick={resetCustomTheme}
            className={cn(
              "flex items-center justify-center rounded-lg text-muted transition-colors hover:bg-card hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
              compact ? "size-7" : "size-9",
            )}
          >
            <RotateCcw className={compact ? "size-3.5" : "size-4"} strokeWidth={1.8} />
          </button>
        </div>
      </div>

      <div className={cn("grid grid-cols-8", compact ? "mt-2 gap-1.5" : "mt-4 gap-2")}>
        {CUSTOM_THEME_SWATCHES.map((color) => (
          <button
            key={color}
            type="button"
            title={color}
            aria-label={`使用颜色 ${color}`}
            aria-pressed={customTheme.accent === color}
            onClick={() => setCustomAccent(color)}
            className={cn(
              "aspect-square w-full rounded-full border border-black/10 shadow-sm transition-transform hover:scale-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
              customTheme.accent === color && "ring-2 ring-primary ring-offset-2 ring-offset-card",
            )}
            style={{ backgroundColor: color }}
          />
        ))}
      </div>

      <label
        className={cn(
          "mt-3 flex cursor-pointer items-center justify-between gap-3 rounded-lg bg-card text-ink-2 transition-colors hover:text-ink",
          compact ? "h-8 px-2 text-[11px]" : "h-10 px-3 text-sm",
        )}
      >
        <span>任意颜色</span>
        <span className="flex items-center gap-2 font-mono text-muted">
          {customTheme.accent}
          <input
            type="color"
            value={customTheme.accent}
            onChange={(event) => setCustomAccent(event.target.value.toUpperCase())}
            aria-label="选择任意自定义颜色"
            className="size-6 cursor-pointer appearance-none overflow-hidden rounded-md border-0 bg-transparent p-0"
          />
        </span>
      </label>
    </div>
  );
}
