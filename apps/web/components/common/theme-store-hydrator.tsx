"use client";

import { useEffect } from "react";
import { hydrateThemeStoreFromStorage } from "@/stores/theme";

/** Sync Zustand theme state after hydration; keeps SSR and first client render aligned. */
export function ThemeStoreHydrator() {
  useEffect(() => {
    hydrateThemeStoreFromStorage();
  }, []);
  return null;
}
