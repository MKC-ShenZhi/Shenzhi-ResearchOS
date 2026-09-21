import { AppShell } from "@/components/common/layout/app-shell";
import { ScholarDetailPage } from "@/features/knowledge/scholars/ScholarDetailPage";
import { scholarIdFromRouteParam } from "@/lib/navigation/scholar";

export default async function Page({ params }: {
  params: Promise<{ scholarId: string }>;
}) {
  const { scholarId } = await params;
  return (
    <AppShell>
      <ScholarDetailPage scholarId={scholarIdFromRouteParam(scholarId)} />
    </AppShell>
  );
}
