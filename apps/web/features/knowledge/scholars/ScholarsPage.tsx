import { Suspense } from "react";
import { ScholarsBrowser } from "@/features/knowledge/scholars/components/scholars-browser";

/** 学者库 `/knowledge/scholars` —— 正式路径仅使用 Scholar API。 */
export function ScholarsPage() {
  return (
    <div className="flex min-h-[calc(100vh)] items-stretch">
      <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载学者库…</p>}>
        <ScholarsBrowser />
      </Suspense>
    </div>
  );
}
