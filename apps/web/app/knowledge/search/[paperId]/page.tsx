import { redirect } from "next/navigation";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { paperHref, paperIdFromRouteParam } from "@/lib/navigation/paper";

/** Compatibility for bookmarks; normalize the path segment before rebuilding its URL. */
export default async function Page({ params, searchParams }: {
  params: Promise<{ paperId: string }>;
  searchParams?: Promise<{ returnTo?: string | string[] }>;
}) {
  const { paperId: routePaperId } = await params;
  const query = await searchParams;
  redirect(paperHref(paperIdFromRouteParam(routePaperId), normalizeInternalReturnTo(query?.returnTo)));
}
