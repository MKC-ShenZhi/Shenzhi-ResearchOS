import { apiJson } from "@/clients/backend/http";
import type { UserSettings, UserSettingsPatch } from "./types";

export type {
  NotificationKey,
  NotificationPreferences,
  SettingsLocale,
  ThemeMode,
  UserSettings,
  UserSettingsPatch,
} from "./types";

export function getUserSettings() {
  return apiJson<UserSettings>("/settings");
}

export function patchUserSettings(patch: UserSettingsPatch) {
  return apiJson<UserSettings>("/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}
