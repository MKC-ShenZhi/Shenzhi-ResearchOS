"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bookmark, Check, LoaderCircle, MoreHorizontal, Plus, X } from "lucide-react";
import { ApiError } from "@/clients/backend/http";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { useCollections } from "@/stores/collections";

export function CollectionPicker({ paperId, className = "", iconOnly = false }: { paperId: string; className?: string; iconOnly?: boolean }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number; width: number; maxHeight: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const { session, isPending } = useAuth();
  const identityKey = useCollections((state) => state.identityKey);
  const { folders, paperFolders, loadFolders, loadPaperFolders, createFolder, updatePaperFolders } = useCollections();
  const checked = paperFolders[paperId] ?? [];

  useEffect(() => {
    if (isPending || !session?.user?.id || identityKey !== session.user.id) return;
    void loadPaperFolders(paperId).catch(() => {});
  }, [identityKey, isPending, loadPaperFolders, paperId, session?.user?.id]);

  useEffect(() => {
    if (!open) return;
    void Promise.all([loadFolders(), loadPaperFolders(paperId)])
      .then(([, folderIds]) => setSelected(folderIds))
      .catch((error) => setMessage(error instanceof ApiError && error.status === 401 ? "该功能需要登录后使用，请先登录" : "收藏信息加载失败"));
  }, [loadFolders, loadPaperFolders, open, paperId]);

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      const button = buttonRef.current;
      const panel = panelRef.current;
      if (!button || !panel) return;

      const viewport = window.visualViewport;
      const viewportLeft = viewport?.offsetLeft ?? 0;
      const viewportTop = viewport?.offsetTop ?? 0;
      const viewportWidth = viewport?.width ?? window.innerWidth;
      const viewportHeight = viewport?.height ?? window.innerHeight;
      const margin = 8;
      const gap = 8;
      const width = Math.min(288, Math.max(0, viewportWidth - margin * 2));
      const buttonRect = button.getBoundingClientRect();
      if (buttonRect.bottom <= viewportTop || buttonRect.top >= viewportTop + viewportHeight) {
        setOpen(false);
        return;
      }
      const scrollArea = panel.querySelector<HTMLElement>("[data-collection-list]");
      const panelHeight = panel.scrollHeight + Math.max(
        0,
        (scrollArea?.scrollHeight ?? 0) - (scrollArea?.clientHeight ?? 0),
      );
      const spaceBelow = viewportTop + viewportHeight - margin - buttonRect.bottom - gap;
      const spaceAbove = buttonRect.top - (viewportTop + margin) - gap;
      const placeBelow = spaceBelow >= panelHeight || spaceBelow >= spaceAbove;
      const availableHeight = Math.max(0, Math.min(
        viewportHeight - margin * 2,
        placeBelow ? spaceBelow : spaceAbove,
      ));
      const maxHeight = Math.min(panelHeight, availableHeight);
      const left = Math.min(
        Math.max(buttonRect.right - width, viewportLeft + margin),
        viewportLeft + viewportWidth - margin - width,
      );
      const top = Math.min(
        Math.max(
          placeBelow ? buttonRect.bottom + gap : buttonRect.top - gap - maxHeight,
          viewportTop + margin,
        ),
        viewportTop + viewportHeight - margin - maxHeight,
      );

      setPosition((current) => {
        if (current?.top === top && current.left === left &&
            current.width === width && current.maxHeight === maxHeight) return current;
        return { top, left, width, maxHeight };
      });
    };

    updatePosition();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updatePosition);
    if (buttonRef.current) observer?.observe(buttonRef.current);
    if (panelRef.current) observer?.observe(panelRef.current);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    window.visualViewport?.addEventListener("resize", updatePosition);
    window.visualViewport?.addEventListener("scroll", updatePosition);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      window.visualViewport?.removeEventListener("resize", updatePosition);
      window.visualViewport?.removeEventListener("scroll", updatePosition);
    };
  }, [folders.length, message, open]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node &&
          !rootRef.current?.contains(target) &&
          !panelRef.current?.contains(target)) setOpen(false);
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
      if (error instanceof ApiError && error.status === 401) setMessage("该功能需要登录后使用，请先登录");
      else setMessage(error instanceof ApiError && error.status === 409 ? "名称已存在" : "创建文件夹失败");
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
    <div ref={rootRef} data-paper-card-interactive className={`relative inline-flex ${className}`.trim()}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => { setPosition(null); setOpen((value) => !value); setMessage(""); }}
        aria-expanded={open}
        aria-label={iconOnly ? "收藏" : undefined}
        title={iconOnly ? "收藏" : undefined}
        className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg text-[13px] transition-colors ${iconOnly ? "size-8 shrink-0 justify-center" : "px-2 py-1.5"} ${active ? "text-primary" : "text-muted hover:bg-chip"}`}
      >
        <Bookmark className="size-4" fill={active ? "currentColor" : "none"} />
        {!iconOnly && "收藏"}
      </button>
      {open && createPortal(
        <div
          ref={panelRef}
          className="fixed z-50 flex min-h-0 flex-col rounded-xl border border-line bg-card p-3 shadow-card"
          style={{
            top: position?.top ?? 0,
            left: position?.left ?? 0,
            width: position?.width ?? 288,
            maxHeight: position?.maxHeight ?? window.innerHeight,
            visibility: position ? "visible" : "hidden",
          }}
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold text-ink">收藏到文件夹</span>
            <button type="button" onClick={() => setOpen(false)} aria-label="关闭" className="rounded-md p-1 text-faint hover:bg-chip hover:text-ink"><X className="size-4" /></button>
          </div>
          <div data-collection-list className="min-h-0 flex-1 space-y-1 overflow-y-auto">
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
        </div>,
        document.body,
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
