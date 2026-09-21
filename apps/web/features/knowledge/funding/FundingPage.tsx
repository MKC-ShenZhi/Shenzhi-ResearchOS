import { RelatedPaperSearch } from "@/features/knowledge/components/related-paper-search";

/** 项目、专利与基金当前按上游真实 funding query 能力统一检索关联论文。 */
export function FundingPage() {
  return (
    <RelatedPaperSearch kind="funding" />
  );
}
