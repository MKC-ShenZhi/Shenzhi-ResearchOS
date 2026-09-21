import { DeepResearchPageClient } from "@/features/deep-research/components/deep-research-page";

/**
 * Deep Research 页 `/agents/deep-research` —— 研究报告型双栏工作台:
 * 入口态(新建 / 历史)+ Session 态(左栏过程,右栏报告逐节生成)
 */
export function DeepResearchPage() {
  return (
    <DeepResearchPageClient />
  );
}
