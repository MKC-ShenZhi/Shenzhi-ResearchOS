import { Suspense } from "react";
import { AppShell } from "@/components/common/layout/app-shell";
import { KnowledgeDashboard } from "@/features/knowledge/components/knowledge-dashboard";

/** 知识库总览 `/knowledge` —— 跨库搜索 + 五类科研资产工作台 */
export function KnowledgePage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载知识库…</p>}>
        <KnowledgeDashboard />
      </Suspense>
    </AppShell>
  );
}
