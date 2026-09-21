import { AppShell } from "@/components/common/layout/app-shell";
import { ScholarNetwork } from "@/features/knowledge/scholars/graph/components/scholar-network";

// V1 暂停正式接入：上游尚无学者关系图谱 Contract；原型路由保留但不进入产品导航。

/** 学者合作关系图谱示例 —— 与私域论文图谱完全独立 */
export function ScholarGraphPage() {
  return (
    <AppShell>
      <ScholarNetwork />
    </AppShell>
  );
}
