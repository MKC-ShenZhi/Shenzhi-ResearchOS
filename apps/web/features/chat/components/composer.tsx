"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowUp,
  ChevronRight,
  Globe,
  Plus,
  Search,
  Sparkles,
  Square,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { popoverPosition, usePopoverPlacement } from "@/lib/use-popover-placement";
import { DEFAULT_CHAT_MODEL } from "@/lib/data/chat-models";
import { FALLBACK_CHAT_CONFIG } from "@/clients/backend/chat";
import { AttachmentMenu } from "./attachment-menu";
import { ComposerControlPicker } from "./composer-control-picker";
import { questionSchema } from "@/lib/validations";
import type { ComposerEntryMode } from "@/types";
import type {
  ChatAttachment,
  ChatModelId,
  ChatReplyMode,
  ComposerSubmitPayload,
  ChatConfig,
} from "@/types/ai-search";

export type { ComposerEntryMode, ComposerSubmitPayload } from "@/types";

const PLAIN_BTN =
  "flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-xl text-muted transition-colors hover:bg-chip hover:text-ink";

const MODE_PILL =
  "flex h-9 cursor-pointer items-center gap-1.5 rounded-full px-3 text-[13px] font-medium transition-colors";

function SearchModeSwitch({
  mode,
  onChange,
}: {
  mode: ComposerEntryMode;
  onChange: (mode: ComposerEntryMode) => void;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <button
        type="button"
        aria-pressed={mode === "search"}
        onClick={() => onChange("search")}
        className={cn(
          MODE_PILL,
          mode === "search"
            ? "bg-primary-soft text-primary"
            : "text-muted hover:bg-chip hover:text-ink-2",
        )}
      >
        <Search className="size-4 shrink-0" strokeWidth={1.8} />
        简单搜索
      </button>
      <button
        type="button"
        aria-pressed={mode === "ai"}
        onClick={() => onChange("ai")}
        className={cn(
          MODE_PILL,
          mode === "ai"
            ? "bg-violet-100 text-violet-800 dark:bg-violet-950/40 dark:text-violet-200"
            : "text-muted hover:bg-chip hover:text-ink-2",
        )}
      >
        <Sparkles className="size-4 shrink-0" strokeWidth={1.8} />
        智能搜索
      </button>
    </div>
  );
}

function useCloseOnOutside(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, close]);
  return ref;
}

function RightSubmenuRow({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-full cursor-pointer items-center gap-2 rounded-xl px-2.5 text-sm text-ink-2 transition-colors hover:bg-chip"
      >
        <span className="w-10 shrink-0 text-left text-[11px] text-muted">
          {label}
        </span>
        <span className="min-w-0 flex-1 truncate text-left font-medium text-ink">
          {value}
        </span>
        <ChevronRight
          className={cn(
            "size-3.5 shrink-0 text-faint transition-transform",
            open && "rotate-90",
          )}
        />
      </button>
      {open && (
        <div className="absolute bottom-0 left-full z-[130] pl-1">
          {children}
        </div>
      )}
    </div>
  );
}

function PlusMenu({
  webSearch,
  onWebSearchChange,
  knowledgeEnabled,
  onKnowledgeEnabledChange,
}: {
  webSearch: boolean;
  onWebSearchChange: (v: boolean) => void;
  knowledgeEnabled: boolean;
  onKnowledgeEnabledChange: (v: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useCloseOnOutside(open, () => setOpen(false));
  const placement = usePopoverPlacement(open, ref, 200);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        aria-label="更多选项"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          PLAIN_BTN,
          (open || webSearch) && "bg-chip text-ink",
        )}
      >
        <Plus
          className={cn("size-5 transition-transform", open && "rotate-45")}
        />
      </button>
      {open && (
        <div
          className={cn(
            "absolute left-0 z-[120] w-44 rounded-2xl border border-line bg-card p-1.5 shadow-pop",
            popoverPosition(placement),
          )}
        >
          <RightSubmenuRow label="插件" value="即将上线">
            <div className="w-40 rounded-xl border border-line bg-card p-2 text-[11px] text-muted shadow-pop">
              插件市场筹备中
            </div>
          </RightSubmenuRow>
          <RightSubmenuRow label="技能" value="即将上线">
            <div className="w-40 rounded-xl border border-line bg-card p-2 text-[11px] text-muted shadow-pop">
              技能库筹备中
            </div>
          </RightSubmenuRow>
          <button
            type="button"
            onClick={() => onWebSearchChange(!webSearch)}
            className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-xl px-2.5 text-sm transition-colors hover:bg-chip"
          >
            <Globe className="size-4 text-muted" strokeWidth={1.8} />
            <span className="flex-1 text-left text-ink-2">联网搜索</span>
            <span
              className={cn(
                "relative h-5 w-9 shrink-0 rounded-full transition-colors",
                webSearch ? "bg-agent" : "bg-line",
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 size-4 rounded-full bg-white shadow-sm transition-transform",
                  webSearch ? "left-4" : "left-0.5",
                )}
              />
            </span>
          </button>
          <button
            type="button"
            onClick={() => onKnowledgeEnabledChange(!knowledgeEnabled)}
            className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-xl px-2.5 text-sm transition-colors hover:bg-chip"
          >
            <Sparkles className="size-4 text-muted" strokeWidth={1.8} />
            <span className="flex-1 text-left text-ink-2">知识库</span>
            <span className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", knowledgeEnabled ? "bg-agent" : "bg-line")}>
              <span className={cn("absolute top-0.5 size-4 rounded-full bg-white shadow-sm transition-transform", knowledgeEnabled ? "left-4" : "left-0.5")} />
            </span>
          </button>
        </div>
      )}
    </div>
  );
}

export function ComposerShell({
  value,
  onChange,
  onSend,
  placeholder,
  variant = "agent",
  entryMode: entryModeProp,
  onEntryModeChange,
  replyMode: replyModeProp,
  onReplyModeChange,
  model: modelProp,
  onModelChange,
  webSearch: webSearchProp,
  onWebSearchChange,
  knowledgeEnabled: knowledgeEnabledProp,
  onKnowledgeEnabledChange,
  attachments: attachmentsProp,
  onAttachmentsChange,
  config = FALLBACK_CHAT_CONFIG,
  busy = false,
  disabled = false,
  onStop,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: (payload: ComposerSubmitPayload) => void;
  placeholder: string;
  variant?: "home" | "agent";
  entryMode?: ComposerEntryMode;
  onEntryModeChange?: (mode: ComposerEntryMode) => void;
  replyMode?: ChatReplyMode;
  onReplyModeChange?: (mode: ChatReplyMode) => void;
  model?: ChatModelId;
  onModelChange?: (model: ChatModelId) => void;
  webSearch?: boolean;
  onWebSearchChange?: (v: boolean) => void;
  knowledgeEnabled?: boolean;
  onKnowledgeEnabledChange?: (v: boolean) => void;
  attachments?: ChatAttachment[];
  onAttachmentsChange?: (items: ChatAttachment[]) => void;
  config?: ChatConfig;
  busy?: boolean;
  /** Blocks interaction while URL session hydration/stop confirmation runs. */
  disabled?: boolean;
  onStop?: () => void;
}) {
  const isHome = variant === "home";
  const [uploading, setUploading] = useState(false);
  const canSend = Boolean(value.trim()) && !busy && !disabled && !uploading;

  const [innerEntryMode, setInnerEntryMode] = useState<ComposerEntryMode>("ai");
  const [innerMode, setInnerMode] = useState<ChatReplyMode>("fast");
  const [innerDepth, setInnerDepth] = useState<"fast" | "deep">("fast");
  const [innerModel, setInnerModel] = useState<ChatModelId>(DEFAULT_CHAT_MODEL);
  const [innerWeb, setInnerWeb] = useState(false);
  const [innerKnowledgeEnabled, setInnerKnowledgeEnabled] = useState(true);
  const [innerFiles, setInnerFiles] = useState<ChatAttachment[]>([]);
  const [controlOpen, setControlOpen] = useState(false);
  const controlRef = useRef<HTMLDivElement>(null);

  const replyMode = replyModeProp ?? innerMode;
  const entryMode = entryModeProp ?? innerEntryMode;
  const setEntryMode = onEntryModeChange ?? setInnerEntryMode;
  const isSmartSearch = entryMode === "ai";
  const depthMode =
    replyMode === "deep" || replyMode === "fast"
      ? (replyMode as "fast" | "deep")
      : innerDepth;
  const preferredModel = modelProp ?? innerModel;
  const model = config.models.some((option) => option.value === preferredModel && option.enabled)
    ? preferredModel : config.default_model ?? config.models.find((option) => option.enabled)?.value ?? preferredModel;
  const webSearch = webSearchProp ?? innerWeb;
  const knowledgeEnabled = knowledgeEnabledProp ?? innerKnowledgeEnabled;
  const attachments = attachmentsProp ?? innerFiles;

  const setReplyMode = onReplyModeChange ?? setInnerMode;
  const setDepthMode = (v: "fast" | "deep") => {
    setInnerDepth(v);
    if (replyMode === "fast" || replyMode === "deep") setReplyMode(v);
  };
  const setModel = onModelChange ?? setInnerModel;
  const setWebSearch = onWebSearchChange ?? setInnerWeb;
  const setKnowledgeEnabled = onKnowledgeEnabledChange ?? setInnerKnowledgeEnabled;
  const setAttachments = onAttachmentsChange ?? setInnerFiles;

  useEffect(() => {
    if (!controlOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!controlRef.current?.contains(e.target as Node)) {
        setControlOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [controlOpen]);

  const buildPayload = (intent?: ComposerEntryMode): ComposerSubmitPayload => ({
    entryMode: intent ?? entryMode,
    knowledgeEnabled,
    question: value.trim(),
    mode: replyMode,
    model,
    web_search: webSearch,
    attachments,
  });

  const submit = (intent?: ComposerEntryMode) => {
    const parsed = questionSchema.safeParse(value);
    if (!parsed.success || busy || disabled || uploading) return;
    onSend(buildPayload(intent));
  };

  return (
    <div className="relative overflow-visible rounded-2xl border border-line/80 bg-card p-3 shadow-pop">
      {attachments.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {attachments.map((item, i) => (
            <button
              key={`${item.kind}-${item.file_id ?? item.ref_id ?? i}`}
              type="button"
              onClick={() =>
                setAttachments(attachments.filter((_, idx) => idx !== i))
              }
              className="rounded-full bg-chip px-2.5 py-1 text-[11px] text-ink-2 hover:bg-panel"
              disabled={uploading || busy || disabled}
              title={item.warning ? `${item.warning} · 点击移除` : "移除"}
            >
              {item.warning ? "⚠ " : ""}{item.title ?? item.ref_id ?? item.file_id ?? item.kind}
            </button>
          ))}
        </div>
      )}

      <textarea
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (
            e.key === "Enter" &&
            !e.shiftKey &&
            !e.nativeEvent.isComposing
          ) {
            e.preventDefault();
            if (busy || disabled) return;
            if (isHome && entryMode === "search") {
              submit("search");
              return;
            }
            if (isHome && e.altKey) {
              submit("search");
              return;
            }
            submit();
          }
        }}
        placeholder={placeholder}
        rows={2}
        maxLength={2000}
        className="min-h-[3.25rem] w-full resize-none bg-transparent px-0.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-faint"
      />

      <div className="mt-1.5 flex items-center gap-1.5">
        <SearchModeSwitch mode={entryMode} onChange={setEntryMode} />
        <PlusMenu
          webSearch={webSearch}
          onWebSearchChange={setWebSearch}
          knowledgeEnabled={knowledgeEnabled}
          onKnowledgeEnabledChange={setKnowledgeEnabled}
        />
        <AttachmentMenu
          disabled={busy || disabled}
          onUploadingChange={setUploading}
          accept={config.upload.accept.join(",")}
          maxFiles={Math.max(0, config.upload.max_files - attachments.length)}
          maxSizeMb={config.upload.max_size_mb}
          onAdd={(items) =>
            setAttachments([...attachments, ...items].slice(0, config.upload.max_files))
          }
        />
        {isSmartSearch && (
          <div ref={controlRef} className="relative min-w-0 shrink">
            <ComposerControlPicker
              model={model}
              onModelChange={setModel}
              replyMode={replyMode}
              onReplyModeChange={setReplyMode}
              depthMode={depthMode}
              onDepthModeChange={setDepthMode}
              options={config.models}
              quota={config.quota}
              anchorRef={controlRef}
              open={controlOpen}
              onOpenChange={setControlOpen}
            />
          </div>
        )}

        <div className="ml-auto flex shrink-0 items-center gap-2">
          {busy && onStop ? (
            <button
              type="button"
              aria-label="停止生成"
              onClick={onStop}
              className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-ink text-white transition-colors hover:bg-ink/90"
            >
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              aria-label="发送"
              onClick={() => submit()}
              disabled={!canSend}
              className={cn(
                "flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors",
                canSend
                  ? "bg-primary text-white hover:bg-primary-deep"
                  : "border border-line bg-chip text-faint",
                !canSend && "cursor-not-allowed",
              )}
            >
              <ArrowUp className="size-4" strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
