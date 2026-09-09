"use client";

import { useEffect, useState } from "react";
import { History, LoaderCircle, Square } from "lucide-react";
import { ApiError } from "@/clients/backend/http";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCollections } from "@/stores/collections";
import { FolderMoreButton } from "./collection-picker";

/** 我的文献库面板 —— 文件夹树 + 标签(对应知识库页面 SVG 第二栏) */
export function LibraryPanel({
  historyActive,
  onHistoryClick,
  selectedFolderId,
  onFolderClick,
}: {
  historyActive: boolean;
  onHistoryClick: () => void;
  selectedFolderId: number | null;
  onFolderClick: (folderId: number) => void;
}) {
  const { folders, loading, loadFolders, createFolder, renameFolder, deleteFolder } = useCollections();
  const [dialog, setDialog] = useState<"create" | "rename" | "delete" | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { void loadFolders(); }, [loadFolders]);

  function openCreate() { setName(""); setError(""); setDialog("create"); }
  function openRename(folderId: number, currentName: string) { setEditingId(folderId); setName(currentName); setError(""); setDialog("rename"); }
  function openDelete(folderId: number) { setEditingId(folderId); setError(""); setDialog("delete"); }

  async function submitDialog() {
    if (dialog === "delete" && editingId !== null) {
      try { await deleteFolder(editingId); if (selectedFolderId === editingId) onFolderClick(folders.find((folder) => folder.id !== editingId)?.id ?? 0); setDialog(null); }
      catch { setError("删除失败，请重试"); }
      return;
    }
    if (!name.trim()) { setError("文件夹名称不能为空"); return; }
    try {
      if (dialog === "create") {
        const folder = await createFolder(name);
        onFolderClick(folder.id);
      } else if (dialog === "rename" && editingId !== null) {
        await renameFolder(editingId, name);
      }
      setDialog(null);
    } catch (reason) {
      setError(reason instanceof ApiError && reason.status === 409 ? "名称已存在，请更换" : "操作失败，请重试");
    }
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col self-stretch border-r border-line bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-bold text-ink">我的文献库</h2>
      </div>

      <button
        type="button"
        onClick={openCreate}
        className="mt-4 flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-primary-soft text-sm font-medium text-primary transition-colors hover:bg-primary-soft/70"
      >
        <Square className="size-3 fill-current" />
        新建文件夹
      </button>

      <p className="mt-2 px-1 text-xs text-faint">文件夹</p>
      <ul className="mt-1.5 space-y-0.5">
        {loading && <li className="flex items-center justify-center py-4 text-xs text-faint"><LoaderCircle className="size-4 animate-spin" /></li>}
        {!loading && folders.length === 0 && <li className="px-2 py-4 text-center text-xs text-faint">暂无文件夹</li>}
        {folders.map((folder) => (
          <li key={folder.id} className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onFolderClick(folder.id)}
              className={cn(
                "flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 rounded-lg px-2 py-2 text-sm transition-colors",
                !historyActive && folder.id === selectedFolderId
                  ? "bg-primary-soft font-medium text-primary"
                  : "text-ink-2 hover:bg-chip",
              )}
            >
              <span
                className={cn(
                  "size-3.5 rounded-[4px]",
                  !historyActive && folder.id === selectedFolderId ? "bg-primary" : "bg-ink-2/70",
                )}
              />
              <span className="flex-1 text-left">{folder.name}</span>
              <span
                className={cn(
                  "text-xs",
                  !historyActive && folder.id === selectedFolderId
                    ? "rounded-full bg-primary px-1.5 py-0.5 leading-none text-white"
                    : "text-faint",
                )}
              >
                {folder.paper_count}
              </span>
            </button>
            <FolderMoreButton onRename={() => openRename(folder.id, folder.name)} onDelete={() => openDelete(folder.id)} />
          </li>
        ))}
      </ul>

      <div className="mt-auto">
        <hr className="mb-3 border-line" />
        
        <button
          type="button"
          onClick={onHistoryClick}
          className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-2 text-sm text-ink-2 transition-colors hover:bg-chip"
        >
          <History className={cn("size-3.5", historyActive && "text-primary")} />
          浏览历史
        </button>
      </div>
      {dialog && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/20 p-4" role="presentation">
          <div className="w-full max-w-sm rounded-2xl bg-card p-5 shadow-card" role="dialog" aria-modal="true">
            <h3 className="text-base font-semibold text-ink">{dialog === "delete" ? "删除文件夹" : dialog === "rename" ? "重命名文件夹" : "新建文件夹"}</h3>
            {dialog === "delete" ? <p className="mt-3 text-sm text-muted">是否确认删除？该操作不可撤回</p> : <input autoFocus value={name} onChange={(event) => setName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void submitDialog(); }} className="mt-4 h-10 w-full rounded-lg border border-line bg-background px-3 text-sm text-ink outline-none focus-visible:border-primary/50" placeholder="文件夹名称" />}
            {error && <p className="mt-2 text-xs text-danger">{error}</p>}
            <div className="mt-5 flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setDialog(null)}>取消</Button><Button type="button" variant={dialog === "delete" ? "danger" : "default"} onClick={() => void submitDialog()}>{dialog === "delete" ? "确认删除" : "确认"}</Button></div>
          </div>
        </div>
      )}
    </aside>
  );
}
