import { FundingPage } from "@/features/knowledge/funding/FundingPage";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ view?: string; q?: string; funding?: string }>;
}) {
  const { view, q, funding } = await searchParams;
  return <FundingPage showFundings={view === "fundings" || Boolean(q || funding)} />;
}
