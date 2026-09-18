"use client";

import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileUp,
  FolderUp,
  History,
  Layers,
  Library,
  Paperclip,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { popoverPosition, usePopoverPlacement } from "@/lib/use-popover-placement";
import { feedPapers } from "@/lib/data/papers";
import { patents } from "@/lib/data/patents";
import { fundings } from "@/lib/data/funding";
import { scholars } from "@/lib/data/scholars";
import { institutions } from "@/lib/data/institutions";
import { projects } from "@/lib/data/projects";
import { uploadFile } from "@/clients/backend/uploads";
import type { ChatAttachment, ChatAttachmentKind } from "@/types/ai-search";

interface RefItem {
  kind: ChatAttachmentKind;
  ref_id: string;
  title: string;
}

interface RefGroup {
  label: string;
  items: RefItem[];
}

const KNOWLEDGE_GROUPS: RefGroup[] = [
  {
    label: "论文库",
    items: feedPapers.slice(0, 3).map((p) => ({
      kind: "paper" as const,
      ref_id: p.id,
      title: p.title,
    })),
  },
  {
    label: "专利库",
    items: patents.slice(0, 3).map((p) => ({
      kind: "patent" as const,
      ref_id: p.id,
      title: p.title,
    })),
  },
  {
    label: "项目基金库",
    items: fundings.slice(0, 3).map((f) => ({
      kind: "funding" as const,
      ref_id: f.id,
      title: f.title,
    })),
  },
  {
    label: "学者关系",
    items: scholars.slice(0, 3).map((s) => ({
      kind: "scholar" as const,
      ref_id: s.id,
      title: `${s.nameCn} · ${s.affiliation}`,
    })),
  },
  {
    label: "研究机构",
    items: institutions.slice(0, 3).map((i) => ({
      kind: "institution" as const,
      ref_id: i.id,
      title: `${i.nameCn} · ${i.type}`,
    })),
  },
];

const HISTORY_GROUPS: RefGroup[] = [
  {
    label: "历史对话",
    items: [
      { kind: "session", ref_id: "demo-ultralong", title: "长上下文 Transformer 调研" },
      { kind: "session", ref_id: "demo-neurips", title: "NeurIPS 2026 投稿筛选" },
      { kind: "session", ref_id: "demo-diffusion", title: "扩散模型效率优化" },
    ],
  },
];

const PROJECT_GROUPS: RefGroup[] = [
  {
    label: "科研项目",
    items: projects.map((p) => ({
      kind: "project" as const,
      ref_id: p.id,
      title: p.name,
    })),
  },
];

function RefPanel({
  groups,
  expandable = false,
  onPick,
}: {
  groups: RefGroup[];
  expandable?: boolean;
  onPick: (item: RefItem) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!expandable) {
    return (
      <div className="w-64 rounded-xl border border-line bg-card p-1.5 shadow-pop">
        {groups.flatMap((group) =>
          group.items.map((item) => (
            <button
              key={item.ref_id}
              type="button"
              onClick={() => onPick(item)}
              className="flex h-8 w-full cursor-pointer items-center rounded-lg px-2.5 text-left text-[13px] text-ink-2 transition-colors hover:bg-chip"
            >
              <span className="truncate">{item.title}</span>
            </button>
          )),
        )}
      </div>
    );
  }

  return (
    <div className="w-64 rounded-xl border border-line bg-card p-1.5 shadow-pop">
      {groups.map((group) => {
        const open = expanded === group.label;
        return (
          <div key={group.label}>
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setExpanded(open ? null : group.label)}
              className="flex h-8 w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 text-[13px] text-ink-2 transition-colors hover:bg-chip"
            >
              <span className="flex-1 truncate text-left">{group.label}</span>
              {open ? (
                <ChevronDown className="size-3.5 text-faint" />
              ) : (
                <ChevronRight className="size-3.5 text-faint" />
              )}
            </button>
            {open && (
              <ul className="mb-1 ml-3 border-l border-line pl-2">
                {group.items.map((item) => (
                  <li key={item.ref_id}>
                    <button
                      type="button"
                      title={item.title}
                      onClick={() => onPick(item)}
                      className="flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs text-muted transition-colors hover:bg-chip hover:text-ink-2"
                    >
                      <BookOpen className="size-3 shrink-0 text-faint" />
                      <span className="truncate">{item.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function AttachmentMenu({
  onAdd,
  onUploadingChange,
  disabled = false,
  accept = ".pdf,.md,.markdown,.txt",
  maxFiles = 5,
  maxSizeMb = 20,
}: {
  onAdd?: (items: ChatAttachment[]) => void;
  onUploadingChange?: (uploading: boolean) => void;
  disabled?: boolean;
  accept?: string;
  maxFiles?: number;
  maxSizeMb?: number;
}) {
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const placement = usePopoverPlacement(open, rootRef, 320);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    folderRef.current?.setAttribute("webkitdirectory", "");
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const pickFiles = async (files: FileList | null) => {
    if (!files || !onAdd) return;
    if (uploading || disabled) return;
    if (!maxFiles) { setUploadError("最多添加 5 个附件，请先移除已有附件"); return; }
    const list = Array.from(files).slice(0, maxFiles);
    const added: ChatAttachment[] = [];
    const errors: string[] = [];
    if (files.length > maxFiles) errors.push(`仅上传前 ${maxFiles} 个文件`);
    setUploading(true); onUploadingChange?.(true); setUploadError("");
    try {
      for (const file of list) {
        if (file.size > maxSizeMb * 1024 * 1024) { errors.push(`${file.name} 超过 ${maxSizeMb}MB`); continue; }
        try {
          const result = await uploadFile(file);
          added.push({ kind: "file", file_id: result.file_id, title: file.name, warning: result.warning });
        } catch (error) { errors.push(error instanceof Error ? error.message : "上传失败"); }
      }
      if (added.length && live.current) onAdd(added);
    } finally {
      setUploadError(errors.join("；"));
      setUploading(false);
      if (live.current) onUploadingChange?.(false);
      if (!errors.length) setOpen(false);
    }
  };

  const addRef = (item: RefItem) => {
    if (uploading || disabled) return;
    if (!maxFiles) { setUploadError("附件数量已达上限"); return; }
    onAdd?.([{ kind: item.kind, ref_id: item.ref_id, title: item.title }]);
    setOpen(false);
  };

  const REF_ITEMS = [
    { label: "引用知识库", icon: Library, groups: KNOWLEDGE_GROUPS, expandable: true },
    { label: "引用历史对话", icon: History, groups: HISTORY_GROUPS },
    { label: "引用科研项目", icon: Layers, groups: PROJECT_GROUPS },
  ];

  return (
    <div ref={rootRef} className="relative">
      <input
        ref={fileRef}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        onChange={(e) => {
          void pickFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <input
        ref={folderRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          void pickFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {uploadError && <p role="alert" className="absolute bottom-full left-0 z-[130] mb-2 w-72 rounded-xl border border-line bg-card p-3 text-xs text-muted shadow-pop">{uploadError}</p>}
      <button
        type="button"
        disabled={disabled}
        aria-label="上传附件"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex size-9 cursor-pointer items-center justify-center rounded-xl text-muted transition-colors hover:bg-chip hover:text-ink",
          open && "bg-chip text-ink",
        )}
      >
        <Paperclip className="size-4.5" strokeWidth={1.8} />
      </button>

      {open && (
        <div
          className={cn(
            "absolute left-0 z-[120] w-52 rounded-xl border border-line bg-card p-1.5 shadow-pop",
            popoverPosition(placement),
          )}
        >
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
            className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm text-ink-2 transition-colors hover:bg-chip"
          >
            <FileUp className="size-4 text-muted" strokeWidth={1.8} />
            {uploading ? "上传中…" : "上传本地文件"}
          </button>
          <button
            type="button"
            disabled={uploading}
            onClick={() => folderRef.current?.click()}
            className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm text-ink-2 transition-colors hover:bg-chip"
          >
            <FolderUp className="size-4 text-muted" strokeWidth={1.8} />
            上传本地文件夹
          </button>

          {REF_ITEMS.map((item) => (
            <div key={item.label} className="group/ref relative">
              <button
                type="button"
                className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm text-ink-2 transition-colors hover:bg-chip group-hover/ref:bg-chip"
              >
                <item.icon className="size-4 text-muted" strokeWidth={1.8} />
                <span className="flex-1 text-left">{item.label}</span>
                <ChevronRight className="size-3.5 text-faint" />
              </button>
              <div className="invisible absolute bottom-0 left-full z-50 pl-1.5 opacity-0 transition-opacity duration-100 group-hover/ref:visible group-hover/ref:opacity-100">
                <RefPanel
                  groups={item.groups}
                  expandable={item.expandable}
                  onPick={addRef}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
