"use client";

import { createContext, useContext, type ReactNode } from "react";
import { createRealScholarProvider } from "./real-provider";
import { previewScholarProvider } from "./preview-provider";
import type { ScholarProvider } from "./types";

const realProvider = createRealScholarProvider();
const defaultProvider = process.env.NODE_ENV === "development" &&
  process.env.NEXT_PUBLIC_SCHOLAR_PREVIEW === "1" ? previewScholarProvider : realProvider;
const ScholarContext = createContext<ScholarProvider>(defaultProvider);

export function ScholarDataProvider({
  children,
  provider = defaultProvider,
}: {
  children: ReactNode;
  provider?: ScholarProvider;
}) {
  return (
    <ScholarContext.Provider value={provider}>
      {children}
    </ScholarContext.Provider>
  );
}

export function useScholarProvider() {
  return useContext(ScholarContext);
}
