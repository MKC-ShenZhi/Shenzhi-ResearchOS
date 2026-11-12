import { Suspense } from "react";
import Link from "next/link";
import { FundingBrowser } from "@/features/knowledge/funding/components/funding-browser";
import { NsfcProjectDirectory } from "@/features/knowledge/nsfc-projects/NsfcProjectDirectory";

export function FundingPage({ showFundings }: { showFundings: boolean }) {
  const tabClass = "border-b-2 px-1 py-3 text-sm font-medium";
  const activeClass = "border-primary text-primary";
  const inactiveClass = "border-transparent text-muted hover:text-ink";

  return (
    <main className="mx-auto w-full max-w-[1080px] space-y-6 px-4 py-8 sm:px-8">
      <h1 className="text-3xl font-bold tracking-tight text-ink">项目基金库</h1>
      <nav aria-label="基金库分类" className="flex flex-wrap gap-x-6 border-b border-line">
        <Link href="/knowledge/funding" aria-current={!showFundings ? "page" : undefined} className={`${tabClass} ${!showFundings ? activeClass : inactiveClass}`}>
          国自然项目
        </Link>
        <Link href="/knowledge/funding?view=fundings" aria-current={showFundings ? "page" : undefined} className={`${tabClass} ${showFundings ? activeClass : inactiveClass}`}>
          基金与关联论文
        </Link>
      </nav>
      <Suspense fallback={<p className="text-sm text-muted">正在加载项目基金库…</p>}>
        {showFundings ? <FundingBrowser /> : <NsfcProjectDirectory />}
      </Suspense>
    </main>
  );
}
