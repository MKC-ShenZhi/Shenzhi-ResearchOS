import type { ReactNode } from "react";
import { AppShell } from "@/components/common/layout/app-shell";

export default function KnowledgeLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
