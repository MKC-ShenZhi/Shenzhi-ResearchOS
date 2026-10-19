import { ScholarDetailPage } from "@/features/knowledge/scholars/ScholarDetailPage";
import { normalizeInternalReturnTo } from "@/lib/navigation/internal-return-to";
import { scholarIdFromRouteParam } from "@/lib/navigation/scholar";

export default async function Page({ params, searchParams }: {
  params: Promise<{ scholarId: string }>;
  searchParams: Promise<{ returnTo?: string }>;
}) {
  const { scholarId } = await params;
  const query = await searchParams;
  return (
    <ScholarDetailPage
      scholarId={scholarIdFromRouteParam(scholarId)}
      returnTo={normalizeInternalReturnTo(query.returnTo)}
    />
  );
}
