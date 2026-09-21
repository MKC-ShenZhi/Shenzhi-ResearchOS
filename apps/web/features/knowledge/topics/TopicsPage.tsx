import { AppShell } from "@/components/common/layout/app-shell";
import { RelatedPaperSearch } from "@/features/knowledge/components/related-paper-search";

export function TopicsPage() {
  return (
    <AppShell>
      <RelatedPaperSearch kind="subject" />
    </AppShell>
  );
}
