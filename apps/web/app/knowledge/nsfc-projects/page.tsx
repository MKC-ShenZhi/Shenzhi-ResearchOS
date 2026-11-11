import { Suspense } from "react";
import { NsfcProjectDirectory } from "@/features/knowledge/nsfc-projects/NsfcProjectDirectory";

export default function Page() {
  return (
    <Suspense fallback={<p className="p-8 text-muted">正在加载国自然项目…</p>}>
      <NsfcProjectDirectory />
    </Suspense>
  );
}
