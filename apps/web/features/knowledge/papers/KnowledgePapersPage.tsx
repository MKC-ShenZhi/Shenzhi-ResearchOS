"use client";

import { useState } from "react";
import { AppShell } from "@/components/common/layout/app-shell";
import { LibraryPanel } from "@/features/knowledge/papers/components/library-panel";
import { LibraryTable } from "@/features/knowledge/papers/components/library-table";
import { ReadingHistory } from "@/features/knowledge/papers/components/reading-history";
import { useCollections } from "@/stores/collections";

/** 论文库页面 `/knowledge/papers` —— 对应「深知-知识库页面.svg」,2026-08-07 由 /knowledge 迁入 */
export function KnowledgePapersPage() {
  const [historyActive, setHistoryActive] = useState(false);
  const [requestedFolderId, setRequestedFolderId] = useState<number | null>(null);
  const folders = useCollections((state) => state.folders);
  const selectedFolderId = folders.some((folder) => folder.id === requestedFolderId)
    ? requestedFolderId : folders[0]?.id ?? null;

  function selectFolder(folderId: number) {
    setRequestedFolderId(folderId);
    setHistoryActive(false);
  }

  return (
    <AppShell>
      <div className="flex min-h-[calc(100vh-3.5rem)] items-stretch lg:h-[100dvh] lg:min-h-0 lg:overflow-hidden">       
        <LibraryPanel historyActive={historyActive} selectedFolderId={selectedFolderId} onFolderClick={selectFolder} onHistoryClick={() => setHistoryActive(true)} />
        {historyActive ? <ReadingHistory /> : <LibraryTable key={selectedFolderId ?? "none"} folderId={selectedFolderId} />}
      </div>
    </AppShell>
  );
}
