"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { InteractionSync } from "./interaction-sync";
import { ReadStatusSync } from "./read-status-sync";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <ReadStatusSync />
      <InteractionSync />
      {children}
    </QueryClientProvider>
  );
}
