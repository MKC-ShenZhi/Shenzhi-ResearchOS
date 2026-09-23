import { Suspense } from "react";
import { AppShell } from "@/components/common/layout/app-shell";
import { FundingBrowser } from "@/features/knowledge/funding/components/funding-browser";

/** 基金候选列表与关联论文。 */
export function FundingPage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载项目基金库…</p>}>
        <FundingBrowser />
      </Suspense>
    </AppShell>
  );
}
