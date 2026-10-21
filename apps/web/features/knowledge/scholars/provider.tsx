"use client";

import { createContext, useContext, type ReactNode } from "react";
import { createRealScholarProvider } from "./real-provider";
import type { ScholarProvider } from "./types";

const realProvider = createRealScholarProvider();
const ScholarContext = createContext<ScholarProvider>(realProvider);

export function ScholarDataProvider({
  children,
  provider = realProvider,
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
