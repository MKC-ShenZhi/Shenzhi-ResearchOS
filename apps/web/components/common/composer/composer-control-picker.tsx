"use client";

import { useState, type RefObject } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { popoverPosition, usePopoverPlacement } from "@/lib/use-popover-placement";
import { ModelProviderLogo } from "./model-provider-logo";
import { QuotaRing } from "./quota-ring";
import type {
  ChatModelId,
  ChatReplyMode,
  ChatConfig,
  ChatModelOption,
} from "@/types/ai-search";

export const STYLE_OPTIONS: {
  value: ChatReplyMode;
  label: string;
  description: string;
}[] = [
  { value: "idea", label: "头脑风暴", description: "发散思路与研究方向" },
  { value: "fast", label: "简明扼要", description: "短平快，适合日常提问" },
  { value: "deep", label: "全面细致", description: "多路检索，适合文献综述" },
  { value: "doubt", label: "严谨质疑", description: "批判性分析与反驳" },
];

function styleLabel(mode: ChatReplyMode) {
  return STYLE_OPTIONS.find((s) => s.value === mode)?.label ?? "简明扼要";
}

function StyleSubmenuRow({
  value,
  onPick,
}: {
  value: string;
  onPick: (v: ChatReplyMode) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="flex h-9 w-full items-center gap-2 rounded-xl px-2.5 text-sm hover:bg-chip">
        <span className="w-10 shrink-0 text-left text-[11px] text-muted">风格</span>
        <span className="min-w-0 flex-1 truncate text-left font-medium text-ink">{value}</span>
        <ChevronRight className={cn("size-3.5 text-faint", open && "rotate-90")} />
      </button>
      {open && <div className="max-h-56 overflow-y-auto rounded-xl bg-panel p-1.5">
        {STYLE_OPTIONS.map((style) => (
          <button key={style.value} type="button" onClick={() => { onPick(style.value); setOpen(false); }}
            className="flex w-full flex-col gap-0.5 rounded-lg px-2.5 py-2 text-left hover:bg-chip">
            <span className="text-sm font-medium text-ink">{style.label}</span>
            <span className="text-[11px] text-muted">{style.description}</span>
          </button>
        ))}
      </div>}
    </div>
  );
}

export function ComposerControlPicker({
  model,
  onModelChange,
  replyMode,
  onReplyModeChange,
  depthMode,
  onDepthModeChange,
  options,
  quota,
  anchorRef,
  open,
  onOpenChange,
}: {
  model: ChatModelId;
  onModelChange: (v: ChatModelId) => void;
  replyMode: ChatReplyMode;
  onReplyModeChange: (v: ChatReplyMode) => void;
  depthMode: "fast" | "deep";
  onDepthModeChange: (v: "fast" | "deep") => void;
  options: ChatModelOption[];
  quota: ChatConfig["quota"];
  anchorRef: RefObject<HTMLDivElement | null>;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [modelsOpen, setModelsOpen] = useState(false);
  const placement = usePopoverPlacement(open, anchorRef, 320);

  const current =
    options.find((m) => m.value === model) ??
    options.find((m) => m.enabled) ??
    options[0];

  const pickDepth = (next: "fast" | "deep") => {
    onDepthModeChange(next);
    if (replyMode === "fast" || replyMode === "deep") {
      onReplyModeChange(next);
    }
  };

  const pickStyle = (v: ChatReplyMode) => {
    onReplyModeChange(v);
    if (v === "fast" || v === "deep") onDepthModeChange(v);
  };

  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`模型与选项：${current?.label ?? ""}`}
        onClick={() => {
          onOpenChange(!open);
          if (open) setModelsOpen(false);
        }}
        className={cn(
          "flex h-8 max-w-[12rem] cursor-pointer items-center gap-1.5 rounded-full border px-3 text-[13px] transition-colors",
          open
            ? "border-primary/40 bg-primary-soft text-primary"
            : "border-line bg-card text-ink hover:border-primary/25 hover:bg-chip",
        )}
      >
        {current && <ModelProviderLogo provider={current.provider} size="sm" />}
        <span className="truncate font-medium">
          {current?.label ?? "选择模型"}
        </span>
        {open ? (
          <ChevronUp className="size-3.5 shrink-0 text-faint" />
        ) : (
          <ChevronDown className="size-3.5 shrink-0 text-faint" />
        )}
      </button>

      {open && (
        <div
          className={cn(
            "absolute left-0 z-[120] w-[min(20rem,calc(100vw-3rem))] overflow-hidden rounded-2xl border border-line bg-card shadow-pop",
            popoverPosition(placement),
          )}
        >
          {!modelsOpen ? (
            <div className="relative p-1.5">
              <div className="absolute right-2.5 top-2.5">
                {quota.limit > 0 && <QuotaRing used={quota.used} limit={quota.limit} size={26} />}
              </div>

              <div className="flex h-9 items-center gap-1.5 px-2.5 pr-12">
                <span className="w-10 shrink-0 text-[11px] text-muted">模式</span>
                <div className="flex rounded-full bg-chip p-0.5">
                  <button
                    type="button"
                    onClick={() => pickDepth("fast")}
                    className={cn(
                      "cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition-colors",
                      depthMode === "fast"
                        ? "bg-card text-primary shadow-sm"
                        : "text-muted hover:text-ink",
                    )}
                  >
                    快速
                  </button>
                  <button
                    type="button"
                    onClick={() => pickDepth("deep")}
                    className={cn(
                      "cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition-colors",
                      depthMode === "deep"
                        ? "bg-card text-primary shadow-sm"
                        : "text-muted hover:text-ink",
                    )}
                  >
                    深度
                  </button>
                </div>
              </div>

              <StyleSubmenuRow
                value={styleLabel(replyMode)}
                onPick={pickStyle}
              />

              <button
                type="button"
                onClick={() => setModelsOpen(true)}
                className="flex h-9 w-full cursor-pointer items-center gap-2 rounded-xl px-2.5 text-sm transition-colors hover:bg-chip"
              >
                <span className="w-10 shrink-0 text-[11px] text-muted">模型</span>
                <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate font-medium text-ink">
                  {current && (
                    <ModelProviderLogo provider={current.provider} size="sm" />
                  )}
                  {current?.label}
                </span>
                <ChevronDown className="size-3.5 shrink-0 text-faint" />
              </button>
            </div>
          ) : (
            <div className="flex max-h-80 flex-col">
              <button
                type="button"
                onClick={() => setModelsOpen(false)}
                className="flex h-9 shrink-0 items-center gap-1.5 border-b border-line px-3 text-[11px] text-muted hover:text-ink"
              >
                <ChevronUp className="size-3.5" />
                返回
              </button>
              <div
                role="listbox"
                className="overflow-y-auto p-1.5"
                aria-label="选择模型"
              >
                {options.map((m) => {
                  const selected = m.value === model;
                  return (
                    <button
                      key={m.value}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      disabled={!m.enabled}
                      title={
                        m.enabled
                          ? undefined
                          : m.reason === "not_subscribed"
                            ? "需要订阅"
                            : "暂不可用"
                      }
                      onClick={() => {
                        if (!m.enabled) return;
                        onModelChange(m.value);
                        setModelsOpen(false);
                        onOpenChange(false);
                      }}
                      className={cn(
                        "mb-1 flex w-full cursor-pointer items-start gap-2.5 rounded-xl border px-2.5 py-2.5 text-left transition-colors last:mb-0",
                        !m.enabled && "cursor-not-allowed opacity-50",
                        selected
                          ? "border-primary/35 bg-primary-soft"
                          : "border-transparent hover:bg-chip",
                      )}
                    >
                      <ModelProviderLogo provider={m.provider} />
                      <span className="min-w-0 flex-1">
                        <span
                          className={cn(
                            "block text-sm font-semibold leading-tight",
                            selected ? "text-primary" : "text-ink",
                          )}
                        >
                          {m.label}
                        </span>
                        {m.description && (
                          <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                            {m.description}
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
              <div className="shrink-0 border-t border-line px-3 py-2 text-[11px] text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Sparkles className="size-3.5 text-agent" />
                  可用模型由后端管理员配置
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}

export { styleLabel };
