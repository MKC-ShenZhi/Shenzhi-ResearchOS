export const THEME_PRESETS = [
  { id: "shenzhi", label: "深知", description: "现有方案" },
  { id: "gpt", label: "GPT", description: "中性工具感" },
  { id: "claude", label: "Claude", description: "温暖书写感" },
  { id: "alphaxiv", label: "alphaXiv", description: "学术编辑感" },
  { id: "apple-light", label: "Apple 浅色", description: "通透冷光" },
  { id: "apple-dark", label: "Apple 深色", description: "深空高光" },
] as const;

export type ThemePreset = (typeof THEME_PRESETS)[number]["id"];

export function isThemePreset(value: string | null): value is ThemePreset {
  return THEME_PRESETS.some((preset) => preset.id === value);
}
