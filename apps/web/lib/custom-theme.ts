export type CustomThemeAppearance = "light" | "dark";

export interface CustomThemeConfig {
  accent: string;
  appearance: CustomThemeAppearance;
}

export const DEFAULT_CUSTOM_THEME: CustomThemeConfig = {
  accent: "#6D5DFB",
  appearance: "light",
};

export const CUSTOM_THEME_STORAGE_KEY = "shenzhi-theme-custom";
export const CUSTOM_THEME_VARS_STORAGE_KEY = "shenzhi-theme-custom-vars";

export const CUSTOM_THEME_SWATCHES = [
  "#E5484D",
  "#F05A28",
  "#F59E0B",
  "#D4A72C",
  "#84CC16",
  "#22A06B",
  "#00A67E",
  "#0EA5A8",
  "#06B6D4",
  "#2F80ED",
  "#315EFB",
  "#635BFF",
  "#8B5CF6",
  "#A855F7",
  "#D946EF",
  "#EC4899",
] as const;

export const CUSTOM_THEME_VARIABLES = [
  "--color-background",
  "--color-sidebar",
  "--color-card",
  "--color-primary",
  "--color-primary-deep",
  "--color-primary-foreground",
  "--color-primary-soft",
  "--color-agent",
  "--color-agent-soft",
  "--color-brand-violet",
  "--color-brand-cyan",
  "--color-brand-gold",
  "--color-ink",
  "--color-ink-2",
  "--color-muted",
  "--color-faint",
  "--color-chip",
  "--color-panel",
  "--color-line",
  "--color-danger",
  "--color-danger-soft",
  "--color-success",
  "--color-success-soft",
  "--shadow-card",
  "--shadow-pop",
  "--page-wallpaper",
  "--surface-card-image",
  "--surface-panel-image",
  "--surface-sidebar-image",
  "--surface-chip-image",
] as const;

type Rgb = { r: number; g: number; b: number };
type Hsl = { h: number; s: number; l: number };

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function normalizeHex(value: string) {
  const hex = value.trim().toUpperCase();
  return /^#[0-9A-F]{6}$/.test(hex) ? hex : DEFAULT_CUSTOM_THEME.accent;
}

function hexToRgb(hex: string): Rgb {
  const value = normalizeHex(hex);
  return {
    r: Number.parseInt(value.slice(1, 3), 16),
    g: Number.parseInt(value.slice(3, 5), 16),
    b: Number.parseInt(value.slice(5, 7), 16),
  };
}

function rgbToHsl({ r, g, b }: Rgb): Hsl {
  const red = r / 255;
  const green = g / 255;
  const blue = b / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const delta = max - min;
  let hue = 0;

  if (delta) {
    if (max === red) hue = ((green - blue) / delta) % 6;
    else if (max === green) hue = (blue - red) / delta + 2;
    else hue = (red - green) / delta + 4;
    hue = Math.round(hue * 60);
    if (hue < 0) hue += 360;
  }

  const lightness = (max + min) / 2;
  const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1));
  return { h: hue, s: saturation * 100, l: lightness * 100 };
}

function hsl(h: number, s: number, l: number, alpha?: number) {
  const hue = ((Math.round(h) % 360) + 360) % 360;
  const value = `${hue} ${Math.round(clamp(s, 0, 100))}% ${Math.round(clamp(l, 0, 100))}%`;
  return alpha === undefined ? `hsl(${value})` : `hsl(${value} / ${alpha})`;
}

function primaryLightness(hue: number) {
  if (hue >= 42 && hue <= 78) return 34;
  if (hue >= 165 && hue <= 205) return 36;
  return 46;
}

export function normalizeCustomThemeConfig(value: Partial<CustomThemeConfig> | null | undefined): CustomThemeConfig {
  return {
    accent: normalizeHex(value?.accent ?? DEFAULT_CUSTOM_THEME.accent),
    appearance: value?.appearance === "dark" ? "dark" : "light",
  };
}

export function createCustomThemeVariables(input: CustomThemeConfig): Record<string, string> {
  const config = normalizeCustomThemeConfig(input);
  const { h, s } = rgbToHsl(hexToRgb(config.accent));
  const saturation = clamp(s, 58, 88);
  const shiftedHue = (h + 28) % 360;
  const violetHue = h >= 230 && h <= 310 ? h : (h + 78) % 360;
  const cyanHue = h >= 165 && h <= 205 ? h : (h + 155) % 360;

  if (config.appearance === "dark") {
    return {
      "--color-background": hsl(h, 28, 5),
      "--color-sidebar": hsl(h, 27, 9),
      "--color-card": hsl(h, 25, 14),
      "--color-primary": hsl(h, saturation, 71),
      "--color-primary-deep": hsl(h, saturation, 59),
      "--color-primary-foreground": hsl(h, 38, 8),
      "--color-primary-soft": hsl(h, 46, 25),
      "--color-agent": hsl(shiftedHue, 72, 70),
      "--color-agent-soft": hsl(shiftedHue, 42, 23),
      "--color-brand-violet": hsl(violetHue, 78, 73),
      "--color-brand-cyan": hsl(cyanHue, 72, 68),
      "--color-brand-gold": hsl(47, 84, 67),
      "--color-ink": hsl(h, 25, 96),
      "--color-ink-2": hsl(h, 18, 78),
      "--color-muted": hsl(h, 14, 61),
      "--color-faint": hsl(h, 15, 41),
      "--color-chip": hsl(h, 28, 19),
      "--color-panel": hsl(h, 38, 21),
      "--color-line": hsl(h, 23, 29),
      "--color-danger": "#FF7A82",
      "--color-danger-soft": "#442129",
      "--color-success": "#61D5A5",
      "--color-success-soft": "#173A30",
      "--shadow-card": "0 4px 18px rgb(0 0 0 / 0.48)",
      "--shadow-pop": "0 20px 50px rgb(0 0 0 / 0.66)",
      "--page-wallpaper": `radial-gradient(circle at 88% 3%, ${hsl(h, saturation, 58, 0.3)}, transparent 27rem), radial-gradient(circle at 68% 0%, ${hsl(shiftedHue, 76, 58, 0.14)}, transparent 36rem)`,
      "--surface-card-image": `linear-gradient(132deg, ${hsl(h, saturation, 58, 0.17)}, transparent 42%, ${hsl(shiftedHue, 76, 58, 0.06)})`,
      "--surface-panel-image": `linear-gradient(135deg, ${hsl(h, saturation, 58, 0.17)}, ${hsl(shiftedHue, 76, 58, 0.07)})`,
      "--surface-sidebar-image": `linear-gradient(180deg, ${hsl(h, saturation, 58, 0.19)}, transparent 60%)`,
      "--surface-chip-image": `linear-gradient(135deg, ${hsl(h, saturation, 58, 0.19)}, ${hsl(shiftedHue, 76, 58, 0.08)})`,
    };
  }

  const primaryL = primaryLightness(h);
  return {
    "--color-background": hsl(h, 42, 97),
    "--color-sidebar": hsl(h, 48, 89),
    "--color-card": hsl(h, 48, 95),
    "--color-primary": hsl(h, saturation, primaryL),
    "--color-primary-deep": hsl(h, saturation, primaryL - 10),
    "--color-primary-foreground": "#FFFFFF",
    "--color-primary-soft": hsl(h, 72, 88),
    "--color-agent": hsl(shiftedHue, 58, 39),
    "--color-agent-soft": hsl(shiftedHue, 45, 91),
    "--color-brand-violet": hsl(violetHue, 52, 48),
    "--color-brand-cyan": hsl(cyanHue, 58, 36),
    "--color-brand-gold": hsl(43, 75, 41),
    "--color-ink": hsl(h, 24, 14),
    "--color-ink-2": hsl(h, 16, 31),
    "--color-muted": hsl(h, 12, 46),
    "--color-faint": hsl(h, 12, 65),
    "--color-chip": hsl(h, 44, 90),
    "--color-panel": hsl(h, 52, 87),
    "--color-line": hsl(h, 31, 80),
    "--color-danger": "#C84049",
    "--color-danger-soft": "#F8E1E3",
    "--color-success": "#347A5B",
    "--color-success-soft": "#E1EFE7",
    "--shadow-card": `0 4px 14px ${hsl(h, 42, 30, 0.08)}`,
    "--shadow-pop": `0 18px 42px ${hsl(h, 42, 30, 0.15)}`,
    "--page-wallpaper": `radial-gradient(circle at 88% 5%, ${hsl(h, saturation, 58, 0.22)}, transparent 27rem), radial-gradient(circle at 68% 0%, ${hsl(shiftedHue, 76, 64, 0.13)}, transparent 35rem)`,
    "--surface-card-image": `linear-gradient(135deg, rgb(255 255 255 / 0.72), ${hsl(h, saturation, 58, 0.16)})`,
    "--surface-panel-image": `linear-gradient(135deg, ${hsl(h, saturation, 58, 0.22)}, ${hsl(shiftedHue, 76, 64, 0.1)})`,
    "--surface-sidebar-image": `linear-gradient(180deg, ${hsl(h, saturation, primaryL, 0.22)}, transparent 68%)`,
    "--surface-chip-image": `linear-gradient(135deg, ${hsl(h, saturation, 58, 0.22)}, ${hsl(shiftedHue, 76, 64, 0.1)})`,
  };
}
