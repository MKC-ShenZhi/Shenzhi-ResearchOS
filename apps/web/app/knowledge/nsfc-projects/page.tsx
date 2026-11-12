import { redirect } from "next/navigation";
import { nsfcDirectoryHref } from "@/features/knowledge/nsfc-projects/navigation";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>;
}) {
  const { q, page } = await searchParams;
  redirect(nsfcDirectoryHref(typeof q === "string" ? q : "", typeof page === "string" ? page : undefined));
}
