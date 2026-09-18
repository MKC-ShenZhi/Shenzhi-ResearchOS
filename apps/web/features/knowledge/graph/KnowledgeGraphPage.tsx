import { AppShell } from "@/components/common/layout/app-shell";
import { GraphPageLayout } from "@/components/common/graph/graph-page-layout";
import { privateGraph } from "@/features/knowledge/data-knowledge-graph";

/** 私域知识图谱 `/knowledge/graph` —— 我的发表 × 收藏论文 分层双色图 */
export function KnowledgeGraphPage() {
  return (
    <AppShell>
      <div className="flex h-[calc(100dvh-3.5rem)] flex-col bg-background lg:h-screen">
        <GraphPageLayout
          graph={privateGraph}
          mode="strata"
          backHref="/knowledge"
          backLabel="返回知识库"
          title="私域知识图谱"
        />
      </div>
    </AppShell>
  );
}
