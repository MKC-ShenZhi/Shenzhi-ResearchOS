import { redirect } from "next/navigation";
import { scholarHref, scholarIdFromRouteParam } from "@/lib/navigation/scholar";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(scholarHref(scholarIdFromRouteParam(id)));
}
