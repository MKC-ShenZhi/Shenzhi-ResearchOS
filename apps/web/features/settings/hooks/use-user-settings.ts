"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import {
  getUserSettings,
  patchUserSettings,
  type NotificationPreferences,
  type SettingsLocale,
  type UserSettingsPatch,
} from "@/clients/backend/settings";
import { useThemeStore, type ThemeMode } from "@/stores/theme";
import { readLocalLocale, storeLocalLocale } from "../i18n";

const DEFAULT_NOTIFICATIONS: NotificationPreferences = {
  activity: true,
  subscription: true,
  interaction: true,
  system: true,
};

export function useUserSettings() {
  const { session, isPending } = useAuth();
  const themeMode = useThemeStore((state) => state.mode);
  const setThemeMode = useThemeStore((state) => state.setMode);
  // Match the server render first; hydrate the browser preference in the deferred effect below.
  const [locale, setLocaleState] = useState<SettingsLocale>("zh-CN");
  const [notifications, setNotifications] = useState(DEFAULT_NOTIFICATIONS);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setLocaleState(readLocalLocale()), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (isPending) return;
    let cancelled = false;
    const load = async () => {
      if (!session?.user.id) {
        if (!cancelled) setLoading(false);
        return;
      }
      if (!cancelled) setLoading(true);
      try {
        const settings = await getUserSettings();
        if (cancelled) return;
        setLocaleState(settings.locale);
        storeLocalLocale(settings.locale);
        setThemeMode(settings.theme_mode);
        setNotifications(settings.notifications);
        setError(null);
      } catch {
        if (!cancelled) setError("load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void Promise.resolve().then(load);
    return () => {
      cancelled = true;
    };
  }, [isPending, session?.user.id, setThemeMode]);

  const persist = useCallback(
    async (patch: UserSettingsPatch) => {
      if (!session?.user.id) {
        setNotice("local");
        setError(null);
        return true;
      }
      try {
        await patchUserSettings(patch);
        setNotice("saved");
        setError(null);
        return true;
      } catch {
        setNotice(null);
        setError("save");
        return false;
      }
    },
    [session?.user.id],
  );

  const setLocale = useCallback(async (next: SettingsLocale) => {
    const previous = locale;
    setLocaleState(next);
    storeLocalLocale(next);
    if (!(await persist({ locale: next })) && session?.user.id) {
      setLocaleState(previous);
      storeLocalLocale(previous);
    }
  }, [locale, persist, session?.user.id]);

  const setTheme = useCallback(async (next: ThemeMode) => {
    const previous = themeMode;
    setThemeMode(next);
    if (!(await persist({ theme_mode: next })) && session?.user.id) setThemeMode(previous);
  }, [persist, session?.user.id, setThemeMode, themeMode]);

  const setNotificationPreferences = useCallback(async (next: NotificationPreferences) => {
    const previous = notifications;
    setNotifications(next);
    if (!(await persist({ notifications: next })) && session?.user.id) setNotifications(previous);
  }, [notifications, persist, session?.user.id]);

  return {
    locale,
    themeMode,
    notifications,
    loading,
    notice,
    error,
    isAuthenticated: Boolean(session?.user.id),
    setLocale,
    setTheme,
    setNotifications: setNotificationPreferences,
  };
}
