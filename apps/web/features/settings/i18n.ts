import type { SettingsLocale } from "@/clients/settings";

export const LOCALE_STORAGE_KEY = "shenzhi-settings-locale";

export const settingsMessages = {
  "zh-CN": {
    title: "设置",
    profile: "个人",
    subscription: "订阅",
    usage: "用量统计",
    agent: "Agent 设置",
    mcp: "MCP",
    api: "API",
    notifications: "通知",
    profileIntro: "基本资料",
    account: "账户",
    language: "语言",
    appearance: "外观",
    profileEmpty: "尚未填写学者简介。当前仅展示账户中的真实基本资料。",
    avatarNote: "头像来自账户资料；上传能力尚未启用。",
    signInProfile: "登录后可查看真实账户资料和同步偏好。",
    saved: "偏好设置已保存",
    localOnly: "当前未登录，偏好仅保存在此浏览器。",
    saveFailed: "服务端暂时不可用，已保留本地设置，请稍后重试。",
  },
  en: {
    title: "Settings",
    profile: "Profile",
    subscription: "Subscription",
    usage: "Usage",
    agent: "Agent settings",
    mcp: "MCP",
    api: "API",
    notifications: "Notifications",
    profileIntro: "Basic profile",
    account: "Account",
    language: "Language",
    appearance: "Appearance",
    profileEmpty: "No scholar bio has been added. Only verified account details are shown.",
    avatarNote: "This avatar comes from your account. Upload is not available yet.",
    signInProfile: "Sign in to view account details and sync preferences.",
    saved: "Preferences saved",
    localOnly: "You are signed out. Preferences are stored in this browser only.",
    saveFailed: "The server is unavailable. Your local preference was kept; please retry later.",
  },
} as const;

export function readLocalLocale(): SettingsLocale {
  if (typeof window === "undefined") return "zh-CN";
  try {
    if (localStorage.getItem(LOCALE_STORAGE_KEY) === "en") return "en";
  } catch {
    // Fall through to the same-origin cookie fallback.
  }
  return document.cookie.split(";").some((item) => item.trim() === `${LOCALE_STORAGE_KEY}=en`)
    ? "en"
    : "zh-CN";
}

export function storeLocalLocale(locale: SettingsLocale) {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Browser privacy modes may disable local storage.
  }
  document.cookie = `${LOCALE_STORAGE_KEY}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`;
}
