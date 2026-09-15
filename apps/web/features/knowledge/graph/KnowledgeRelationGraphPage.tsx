import { AppShell } from "@/components/common/layout/app-shell";
import { KnowledgeGraphWorkbench } from "./components/graph-workbench";

/** 论文关系图谱页 `/papers/[id]/graph` —— 三栏图谱工作台 */
export function KnowledgeRelationGraphPage({ paperId, returnTo }: { paperId: string; returnTo?: string | null }) {
  return (
    <AppShell>
      <div className="flex h-[calc(100dvh-3.5rem)] flex-col bg-background lg:h-screen">
        {/* key=paperId：切换中心论文时重挂载，重置选择 / 方向 / 布局状态 */}
        <KnowledgeGraphWorkbench key={paperId} paperId={paperId} returnTo={returnTo} />
      </div>
    </AppShell>
  );
}
