"use client";

import { useState } from "react";
import { AppShell } from "@/components/common/layout/app-shell";
import { LibraryPanel } from "@/features/knowledge/papers/components/library-panel";
import { LibraryTable } from "@/features/knowledge/papers/components/library-table";
import { ReadingHistory } from "@/features/knowledge/papers/components/reading-history";

/** 论文库页面 `/knowledge/papers` —— 对应「深知-知识库页面.svg」,2026-08-07 由 /knowledge 迁入 */
export function KnowledgePapersPage() {
  const [historyActive, setHistoryActive] = useState(false);

  return (
    <AppShell>
      <div className="flex min-h-[calc(100vh)] items-stretch">
        <LibraryPanel historyActive={historyActive} onHistoryClick={() => setHistoryActive(true)} />
        {historyActive ? <ReadingHistory /> : <LibraryTable />}
      </div>
    </AppShell>
  );
}
