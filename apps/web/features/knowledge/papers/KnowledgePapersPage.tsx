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
  const [preferredFolderId, setPreferredFolderId] = useState<number | null>(null);
  const folders = useCollections((state) => state.folders);
  const selectedFolderId = preferredFolderId !== null
    && folders.some((folder) => folder.id === preferredFolderId)
    ? preferredFolderId
    : folders[0]?.id ?? null;

  function selectFolder(folderId: number) {
    setPreferredFolderId(folderId);
    setHistoryActive(false);
  }

  return (
    <AppShell>
      <div className="flex min-h-[calc(100vh)] items-stretch">
        <LibraryPanel historyActive={historyActive} selectedFolderId={selectedFolderId} onFolderClick={selectFolder} onHistoryClick={() => setHistoryActive(true)} />
        {historyActive ? <ReadingHistory /> : <LibraryTable folderId={selectedFolderId} />}
      </div>
    </AppShell>
  );
}
