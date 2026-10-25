"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bookmark, Check, LoaderCircle, MoreHorizontal, Plus, X } from "lucide-react";
import { ApiError } from "@/clients/backend/http";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { usePaperInteraction } from "@/features/knowledge/interactions/use-paper-interaction";
import { useRefreshPaperInteraction } from "@/features/knowledge/interactions/use-refresh-paper-interaction";
import { useCollections } from "@/stores/collections";

export function CollectionPicker({
  paperId,
  className = "",
  iconOnly = false,
  onOpenChange,
}: {
  paperId: string;
  className?: string;
  iconOnly?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const { session, isPending: isAuthPending, openLogin } = useAuth();
  const { interaction, refetch: refetchInteraction } = usePaperInteraction(paperId);
  const refreshInteraction = useRefreshPaperInteraction(paperId);
  const { folders, loadFolders, createFolder, updatePaperFolders } = useCollections();
  const checked = interaction?.folderIds ?? [];

  const promptLogin = useCallback(() => {
    changeOpen(false);
    setMessage("");
    openLogin({
      notice: "登录后即可收藏论文",
      // 登录成功只把论文上下文带回选择器，收藏仍需用户确认。
      onSuccess: () => changeOpen(true),
    });
  }, [openLogin, onOpenChange]);
  function changeOpen(nextOpen: boolean) {
    setOpen(nextOpen);
    onOpenChange?.(nextOpen);
  }

  useEffect(() => {
    if (!open) return;
    void Promise.all([loadFolders(), refetchInteraction()])
      .then(([, result]) => setSelected(result.data?.folderIds ?? []))
      .catch((error) => {
        if (error instanceof ApiError && error.status === 401) {
          promptLogin();
          return;
        }
        setMessage("收藏信息加载失败");
      });
  }, [loadFolders, open, promptLogin, refetchInteraction]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        changeOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [onOpenChange, open]);

  async function addFolder() {
    const value = name.trim();
    if (!value) return;
    try {
      const folder = await createFolder(value);
      setSelected((current) => [...current, folder.id]);
      setName("");
      setMessage("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) promptLogin();
      else setMessage(error instanceof ApiError && error.status === 409 ? "名称已存在" : "创建文件夹失败");
    }
  }

  async function save() {
    setSaving(true);
    setMessage("");
    try {
      await updatePaperFolders(paperId, selected);
      changeOpen(false);
      // 人数以服务端重新统计的结果为准。
      void refreshInteraction();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) promptLogin();
      else setMessage("操作失败，请重试");
    } finally {
      setSaving(false);
    }
  }

  function handleTrigger() {
    if (isAuthPending) return;
    setMessage("");
    if (!session) {
      openLogin({
        notice: "登录后即可收藏论文",
        onSuccess: () => changeOpen(true),
      });
      return;
    }
    changeOpen(!open);
  }

  const active = checked.length > 0;
  return (
    <div ref={rootRef} data-paper-card-interactive data-collection-picker-open={open || undefined} className={`relative inline-flex ${className}`.trim()}>
      <button
        type="button"
        onClick={handleTrigger}
        aria-expanded={open}
        aria-label={iconOnly ? "收藏" : undefined}
        title={iconOnly ? "收藏" : undefined}
        className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg text-[13px] transition-colors ${iconOnly ? "size-8 shrink-0 justify-center" : "px-2 py-1.5"} ${active ? "text-primary" : "text-muted hover:bg-chip"}`}
      >
        <Bookmark className="size-4" fill={active ? "currentColor" : "none"} />
        {!iconOnly && "收藏"}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-[min(18rem,calc(100vw-4.5rem))] rounded-xl border border-line bg-card p-3 shadow-card">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold text-ink">收藏到文件夹</span>
            <button type="button" onClick={() => changeOpen(false)} aria-label="关闭" className="rounded-md p-1 text-faint hover:bg-chip hover:text-ink"><X className="size-4" /></button>
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
            <Button type="button" variant="ghost" size="sm" onClick={() => changeOpen(false)}>取消</Button>
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
