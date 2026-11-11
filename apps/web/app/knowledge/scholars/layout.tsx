import type { ReactNode } from "react";
import { ScholarDataProvider } from "@/features/knowledge/scholars/provider";

export default function ScholarsLayout({ children }: { children: ReactNode }) {
  return <ScholarDataProvider>{children}</ScholarDataProvider>;
}
