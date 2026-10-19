"use client";

import { createContext, useContext, type ReactNode } from "react";
import { createMockScholarProvider } from "./mock-provider";
import type { ScholarProvider } from "./types";

const mockProvider = createMockScholarProvider();
const ScholarContext = createContext<ScholarProvider>(mockProvider);

export function ScholarDataProvider({
  children,
  provider = mockProvider,
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
