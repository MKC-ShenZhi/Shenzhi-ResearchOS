import { Suspense } from "react";
import { ScholarsBrowser } from "@/features/knowledge/scholars/components/scholars-browser";

/** 沿用正式路由，V2 预览由学者局部 Provider 供数。 */
export function ScholarsPage() {
  return (
    <div className="flex min-h-[calc(100vh)] items-stretch">
      <Suspense
        fallback={<p className="p-8 text-sm text-muted">正在加载学者库…</p>}
      >
        <ScholarsBrowser />
      </Suspense>
    </div>
  );
}
