import { Suspense } from "react";
import { FundingBrowser } from "@/features/knowledge/funding/components/funding-browser";

/** 项目基金卡片浏览页。 */
export function FundingPage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载项目基金库…</p>}>
      <FundingBrowser />
    </Suspense>
  );
}
