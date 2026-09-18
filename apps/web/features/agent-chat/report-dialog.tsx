"use client";

/**
 * 报告查看器：正文里只留摘要，点"查看报告"在全屏弹层里渲染完整报告。
 *
 * 布局与 SZDR 的报告页一致（research/report-view.tsx）：sticky 侧边目录 + 锚点跳转 +
 * 参考文献列表；这里只是把它放进弹层，并把 action 换成导出。
 */
import { useCallback, useEffect, useState } from "react";
import { FileDown, Printer, X } from "lucide-react";

import { ReportView } from "./report/report-view";
import type { AgentSource } from "@/clients/backend/agent";

export function ReportDialog({ open, onClose, text, sources, title }: {
  open: boolean;
  onClose: () => void;
  text: string;
  sources?: AgentSource[];
  title?: string;
}) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  /** 导出：把渲染后的报告节点连同样式一起塞进单个 HTML 文件下载（无需后端）。 */
  const exportHtml = useCallback(() => {
    const node = document.getElementById("report-dialog-body");
    const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
      .map((element) => element.outerHTML).join("\n");
    const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>${(title ?? "研究报告").replace(/[<>&]/g, "")}</title>${styles}
<style>body{max-width:820px;margin:40px auto;padding:0 20px;background:#fff}
@media print{body{margin:0}}</style></head><body>${node?.innerHTML ?? ""}</body></html>`;
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${(title ?? "report").replace(/[\\/:*?"<>|]/g, "_").slice(0, 60)}.html`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [title]);

  // 早退必须在全部 Hook 之后：Hook 调用顺序在渲染间必须恒定（Rules of Hooks），
  // 此前 return null 写在 useCallback 之前，开关一次弹层就会触发 Hooks 顺序变更报错。
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-sm">
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">{title ?? "研究报告"}</span>
        <button type="button" onClick={exportHtml}
          className="flex shrink-0 cursor-pointer items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-[12px] text-ink-2 transition-colors hover:border-primary/40 hover:text-primary">
          <FileDown className="size-3.5" strokeWidth={2} aria-hidden /> 导出 HTML
        </button>
        <button type="button" onClick={() => window.print()}
          className="flex shrink-0 cursor-pointer items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-[12px] text-ink-2 transition-colors hover:border-primary/40 hover:text-primary">
          <Printer className="size-3.5" strokeWidth={2} aria-hidden /> 打印 / PDF
        </button>
        <button type="button" onClick={() => { navigator.clipboard.writeText(text); setCopied(true); }}
          className="shrink-0 cursor-pointer rounded-lg border border-line px-2.5 py-1 text-[12px] text-ink-2 transition-colors hover:border-primary/40 hover:text-primary">
          {copied ? "已复制" : "复制全文"}
        </button>
        <button type="button" onClick={onClose} aria-label="关闭"
          className="grid size-7 shrink-0 cursor-pointer place-items-center rounded-lg text-muted transition-colors hover:bg-chip hover:text-ink">
          <X className="size-4" />
        </button>
      </div>
      <div className="scrollbar-subtle min-h-0 flex-1 overflow-y-auto px-4 py-5">
        <div id="report-dialog-body" className="mx-auto w-full max-w-[1100px]">
          <ReportView text={text} sources={sources} />
        </div>
      </div>
    </div>
  );
}
