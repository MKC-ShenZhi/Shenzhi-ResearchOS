"use client";

import { useEffect, useRef, useState } from "react";
import { Bookmark, Check, LoaderCircle, MoreHorizontal, Plus, X } from "lucide-react";
import { ApiError } from "@/clients/backend/http";
import { Button } from "@/components/ui/button";
import { useCollections } from "@/stores/collections";

export function CollectionPicker({ paperId }: { paperId: string }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const { folders, paperFolders, loadFolders, loadPaperFolders, createFolder, updatePaperFolders } = useCollections();
  const checked = paperFolders[paperId] ?? [];

  useEffect(() => {
    if (!open) return;
    void Promise.all([loadFolders(), loadPaperFolders(paperId)])
      .then(([, folderIds]) => setSelected(folderIds))
      .catch((error) => setMessage(error instanceof ApiError && error.status === 401 ? "该功能需要登录后使用，请先登录" : "收藏信息加载失败"));
  }, [loadFolders, loadPaperFolders, open, paperId]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  async function addFolder() {
    const value = name.trim();
    if (!value) return;
    try {
      const folder = await createFolder(value);
      setSelected((current) => [...current, folder.id]);
      setName("");
      setMessage("");
    } catch (error) {
      setMessage(error instanceof ApiError && error.status === 409 ? "名称已存在" : "创建文件夹失败");
    }
  }

  async function save() {
    setSaving(true);
    setMessage("");
    try {
      await updatePaperFolders(paperId, selected);
      setOpen(false);
    } catch (error) {
      setMessage(error instanceof ApiError && error.status === 401 ? "该功能需要登录后使用，请先登录" : "操作失败，请重试");
    } finally {
      setSaving(false);
    }
  }

  const active = checked.length > 0;
  return (
    <div ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        onClick={() => { setOpen((value) => !value); setMessage(""); }}
        aria-expanded={open}
        className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] transition-colors ${active ? "text-primary" : "text-muted hover:bg-chip"}`}
      >
        <Bookmark className="size-4" fill={active ? "currentColor" : "none"} />
        收藏
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-72 rounded-xl border border-line bg-card p-3 shadow-card">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold text-ink">收藏到文件夹</span>
            <button type="button" onClick={() => setOpen(false)} aria-label="关闭" className="rounded-md p-1 text-faint hover:bg-chip hover:text-ink"><X className="size-4" /></button>
          </div>
          <div className="max-h-64 space-y-1 overflow-y-auto">
            {folders.length === 0 && <p className="py-3 text-center text-xs text-faint">暂无文件夹</p>}
            {folders.map((folder) => {
              const isChecked = selected.includes(folder.id);
              return (
                <button
                  key={folder.id}
                  type="button"
                  onClick={() => setSelected((current) => isChecked ? current.filter((id) => id !== folder.id) : [...current, folder.id])}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-ink-2 hover:bg-chip"
                >
                  <span className={`flex size-4 items-center justify-center rounded border ${isChecked ? "border-primary bg-primary text-white" : "border-line"}`}>
                    {isChecked && <Check className="size-3" />}
                  </span>
                  <span className="truncate">{folder.name}</span>
                </button>
              );
            })}
          </div>
          <div className="mt-2 flex items-center gap-1.5 border-t border-line pt-2">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void addFolder(); } }}
              placeholder="新建文件夹"
              className="h-8 min-w-0 flex-1 rounded-lg border border-line bg-background px-2.5 text-xs text-ink outline-none placeholder:text-faint focus-visible:border-primary/50"
            />
            <button type="button" onClick={() => void addFolder()} aria-label="新建文件夹" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary hover:bg-primary-soft/70"><Plus className="size-4" /></button>
          </div>
          {message && <p className="mt-2 text-xs text-danger">{message}</p>}
          <div className="mt-3 flex justify-end gap-2 border-t border-line pt-3">
            <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>取消</Button>
            <Button type="button" size="sm" onClick={() => void save()} disabled={saving}>
              {saving && <LoaderCircle className="size-3.5 animate-spin" />}
              确认
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function FolderMoreButton({ onRename, onDelete }: { onRename: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative shrink-0">
      <button type="button" onClick={() => setOpen((value) => !value)} aria-label="文件夹操作" className="rounded-md p-1 text-faint hover:bg-chip hover:text-ink"><MoreHorizontal className="size-4" /></button>
      {open && (
        <span className="absolute right-0 top-full z-20 mt-1 w-24 rounded-lg border border-line bg-card p-1 text-xs shadow-card">
          <button type="button" onClick={() => { setOpen(false); onRename(); }} className="block w-full rounded-md px-2 py-1.5 text-left text-ink-2 hover:bg-chip">重命名</button>
          <button type="button" onClick={() => { setOpen(false); onDelete(); }} className="block w-full rounded-md px-2 py-1.5 text-left text-danger hover:bg-danger-soft">删除</button>
        </span>
      )}
    </span>
  );
}
