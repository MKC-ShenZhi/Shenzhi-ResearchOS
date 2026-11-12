import { NsfcProjectDetail } from "@/features/knowledge/nsfc-projects/NsfcProjectDetail";
import { nsfcDirectoryHref } from "@/features/knowledge/nsfc-projects/navigation";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ awardNumber: string }>;
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>;
}) {
  const [{ awardNumber }, { q, page }] = await Promise.all([params, searchParams]);
  const backHref = nsfcDirectoryHref(typeof q === "string" ? q : "", typeof page === "string" ? page : undefined);
  return <NsfcProjectDetail awardNumber={awardNumber} backHref={backHref} />;
}
