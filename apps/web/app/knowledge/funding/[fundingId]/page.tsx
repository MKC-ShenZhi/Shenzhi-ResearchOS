import { Suspense } from "react";
import { FundDetailPage } from "@/features/knowledge/funding/FundDetailPage";

export default async function Page({ params, searchParams }: {
  params: Promise<{ fundingId: string }>;
  searchParams: Promise<{ name?: string | string[]; q?: string | string[] }>;
}) {
  const [{ fundingId }, query] = await Promise.all([params, searchParams]);
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted">正在加载基金详情…</p>}>
      <FundDetailPage
        fundingId={fundingId}
        name={typeof query.name === "string" ? query.name : null}
        query={typeof query.q === "string" ? query.q : null}
      />
    </Suspense>
  );
}
