"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  const userId = session?.user.id ?? null;
  const activeUserIdRef = useRef<string | null>(userId);
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
    activeUserIdRef.current = userId;
    return () => {
      activeUserIdRef.current = null;
    };
  }, [userId]);

  useEffect(() => {
    if (isPending) return;
    let cancelled = false;
    const load = async () => {
      if (!userId) {
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
  }, [isPending, setThemeMode, userId]);

  const persist = useCallback(
    async (patch: UserSettingsPatch) => {
      const operationUserId = userId;
      if (!operationUserId) {
        setNotice("local");
        setError(null);
        return true;
      }
      try {
        await patchUserSettings(patch);
        if (activeUserIdRef.current !== operationUserId) return true;
        setNotice("saved");
        setError(null);
        return true;
      } catch {
        if (activeUserIdRef.current !== operationUserId) return true;
        setNotice(null);
        setError("save");
        return false;
      }
    },
    [userId],
  );

  const setLocale = useCallback(async (next: SettingsLocale) => {
    const previous = locale;
    setLocaleState(next);
    storeLocalLocale(next);
    if (!(await persist({ locale: next })) && userId) {
      setLocaleState(previous);
      storeLocalLocale(previous);
    }
  }, [locale, persist, userId]);

  const setTheme = useCallback(async (next: ThemeMode) => {
    const previous = themeMode;
    setThemeMode(next);
    if (!(await persist({ theme_mode: next })) && userId) setThemeMode(previous);
  }, [persist, setThemeMode, themeMode, userId]);

  const setNotificationPreferences = useCallback(async (next: NotificationPreferences) => {
    const previous = notifications;
    setNotifications(next);
    if (!(await persist({ notifications: next })) && userId) setNotifications(previous);
  }, [notifications, persist, userId]);

  return {
    locale,
    themeMode,
    notifications,
    loading,
    notice,
    error,
    isAuthenticated: Boolean(userId),
    setLocale,
    setTheme,
    setNotifications: setNotificationPreferences,
  };
}
