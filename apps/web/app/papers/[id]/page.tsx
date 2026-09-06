import { PaperDetailPage } from "@/features/papers/[id]/PaperDetailPage";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { paperIdFromRouteParam } from "@/lib/navigation/paper";

export default async function Page({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ returnTo?: string | string[] }>;
}) {
  const { id: routePaperId } = await params;
  const query = await searchParams;
  return <PaperDetailPage paperId={paperIdFromRouteParam(routePaperId)} returnTo={normalizeInternalReturnTo(query?.returnTo)} />;
}
