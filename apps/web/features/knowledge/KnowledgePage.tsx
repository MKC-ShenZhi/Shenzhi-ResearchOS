import { Suspense } from "react";
import { AppShell } from "@/components/common/layout/app-shell";
import { KnowledgeDashboard } from "@/features/knowledge/components/knowledge-dashboard";

/** 知识库总览 `/knowledge` —— 真实能力入口，不展示 Mock 资产统计。 */
export function KnowledgePage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载知识库…</p>}>
        <KnowledgeDashboard />
      </Suspense>
    </AppShell>
  );
}
