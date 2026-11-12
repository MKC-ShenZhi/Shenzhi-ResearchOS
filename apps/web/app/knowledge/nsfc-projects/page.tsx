import { redirect } from "next/navigation";
import { nsfcDirectoryHref } from "@/features/knowledge/nsfc-projects/navigation";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[]; keyword?: string | string[] }>;
}) {
  const { q, keyword } = await searchParams;
  redirect(nsfcDirectoryHref(typeof q === "string" ? q : "", typeof keyword === "string" ? keyword : ""));
}
