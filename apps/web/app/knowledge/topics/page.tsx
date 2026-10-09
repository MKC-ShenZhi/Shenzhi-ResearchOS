import { Suspense } from "react";
import { TopicsPage } from "@/features/knowledge/topics/TopicsPage";

export default function Page() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <TopicsPage />
    </Suspense>
  );
}
