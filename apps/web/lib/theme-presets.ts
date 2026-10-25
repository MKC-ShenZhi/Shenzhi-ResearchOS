export const THEME_PRESETS = [
  { id: "shenzhi", label: "深知", description: "现有方案" },
  { id: "gpt", label: "极致黑白", description: "克制灰阶 · 日夜自适应" },
  { id: "warm-teal", label: "青绿", description: "暖白青绿 · 日夜自适应" },
  { id: "blue-teal", label: "墨蓝青绿", description: "墨蓝主调 · 青绿智能强调" },
  { id: "shenzhi-green", label: "深知绿", description: "品牌绿意 · 清爽浅色" },
  { id: "claude", label: "Claude", description: "温暖书写感" },
  { id: "alphaxiv", label: "alphaXiv", description: "学术编辑感" },
  { id: "apple-light", label: "Apple 浅色", description: "通透冷光" },
  { id: "apple-dark", label: "Apple 深色", description: "深空高光" },
  { id: "apple-neo-purple", label: "Neo 紫", description: "亮紫胶囊光" },
  { id: "apple-neo-lime", label: "Neo 青柠", description: "鲜活青柠光" },
  { id: "apple-air-blue", label: "Air 冰蓝", description: "深色金属蓝" },
  { id: "apple-air-violet", label: "Air 紫曜", description: "深色紫曜光" },
  { id: "spectrum-coral", label: "光谱·赤", description: "浅色珊瑚红" },
  { id: "spectrum-amber", label: "光谱·橙", description: "浅色琥珀橙" },
  { id: "spectrum-gold", label: "光谱·金", description: "浅色日光金" },
  { id: "spectrum-emerald", label: "光谱·翠", description: "深色翡翠绿" },
  { id: "spectrum-cyan", label: "光谱·青", description: "浅色湖水青" },
  { id: "spectrum-cobalt", label: "光谱·蓝", description: "深色钴蓝" },
  { id: "spectrum-rose", label: "光谱·玫", description: "深色玫红" },
  { id: "custom", label: "自定义", description: "自由调色板" },
] as const;

export type ThemePreset = (typeof THEME_PRESETS)[number]["id"];

/** Sidebar shortcuts are independent of the full settings catalog. */
export const QUICK_THEME_PRESET_IDS = ["shenzhi", "gpt", "warm-teal", "blue-teal", "shenzhi-green"] as const satisfies readonly ThemePreset[];
export const QUICK_THEME_PRESETS = QUICK_THEME_PRESET_IDS.map((id) => THEME_PRESETS.find((preset) => preset.id === id)!);
// Keep custom recognized for stored preferences and first-paint initialization.
export const VISIBLE_THEME_PRESETS = THEME_PRESETS.filter((preset) => preset.id !== "custom");

export function isThemePreset(value: string | null): value is ThemePreset {
  return THEME_PRESETS.some((preset) => preset.id === value);
}

export function isDarkThemePreset(preset: ThemePreset) {
  return preset === "apple-dark" || preset === "apple-air-blue" || preset === "apple-air-violet" ||
    preset === "spectrum-emerald" || preset === "spectrum-cobalt" || preset === "spectrum-rose";
}

/** 支持日间、夜间及跟随系统；其他探索预设保持原有固定外观。 */
export const MODE_THEME_PRESETS: readonly ThemePreset[] = ["shenzhi", "gpt", "warm-teal"];

export function supportsThemeMode(preset: ThemePreset) {
  return MODE_THEME_PRESETS.includes(preset);
}
