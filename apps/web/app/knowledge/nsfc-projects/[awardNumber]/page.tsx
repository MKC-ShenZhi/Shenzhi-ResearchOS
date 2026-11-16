import { NsfcProjectDetail } from "@/features/knowledge/nsfc-projects/NsfcProjectDetail";
import { nsfcDirectoryHref } from "@/features/knowledge/nsfc-projects/navigation";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ awardNumber: string }>;
  searchParams: Promise<{ q?: string | string[]; keyword?: string | string[] }>;
}) {
  const [{ awardNumber }, { q, keyword }] = await Promise.all([params, searchParams]);
  const backHref = nsfcDirectoryHref(
    typeof q === "string" ? q : "",
    typeof keyword === "string" ? keyword : "",
  );
  return <NsfcProjectDetail awardNumber={awardNumber} backHref={`${backHref}#project-${encodeURIComponent(awardNumber.toUpperCase())}`} />;
}
