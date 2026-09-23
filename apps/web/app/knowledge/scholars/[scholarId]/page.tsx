import { ScholarDetailPage } from "@/features/knowledge/scholars/ScholarDetailPage";
import { scholarIdFromRouteParam } from "@/lib/navigation/scholar";

export default async function Page({ params }: {
  params: Promise<{ scholarId: string }>;
}) {
  const { scholarId } = await params;
  return <ScholarDetailPage scholarId={scholarIdFromRouteParam(scholarId)} />;
}
