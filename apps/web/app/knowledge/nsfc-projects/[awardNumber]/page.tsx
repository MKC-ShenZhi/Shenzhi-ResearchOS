import { NsfcProjectDetail } from "@/features/knowledge/nsfc-projects/NsfcProjectDetail";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ awardNumber: string }>;
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>;
}) {
  const [{ awardNumber }, { q, page }] = await Promise.all([params, searchParams]);
  const back = new URLSearchParams();
  if (typeof q === "string" && q) back.set("q", q);
  if (typeof page === "string" && page) back.set("page", page);
  return <NsfcProjectDetail awardNumber={awardNumber} backHref={`/knowledge/nsfc-projects${back.size ? `?${back}` : ""}`} />;
}
