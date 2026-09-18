import type { ThemeMode } from "@/stores/theme";

export type SettingsLocale = "zh-CN" | "en";
export type NotificationKey =
  | "activity"
  | "subscription"
  | "interaction"
  | "system";

export interface NotificationPreferences {
  activity: boolean;
  subscription: boolean;
  interaction: boolean;
  system: boolean;
}

export interface UserSettings {
  locale: SettingsLocale;
  theme_mode: ThemeMode;
  notifications: NotificationPreferences;
  created_at: string;
  updated_at: string;
}

export interface UserSettingsPatch {
  locale?: SettingsLocale;
  theme_mode?: ThemeMode;
  notifications?: NotificationPreferences;
}
