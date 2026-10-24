"use client";

/**
 * 报告查看器：正文里只留摘要，点"查看报告"在全屏弹层里渲染完整报告。
 *
 * 布局与 SZDR 的报告页一致（research/report-view.tsx）：sticky 侧边目录 + 锚点跳转 +
 * 参考文献列表；这里只是把它放进弹层，并把 action 换成导出。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { FileDown, Printer, X } from "lucide-react";

import { buildReportDocument, reportFileName } from "./report/export-document";
import { ReportView } from "./report/report-view";
import type { AgentSource } from "@/clients/backend/agent";

/** Read CSSOM rules so local HTML files do not depend on /_next stylesheet links. */
async function collectReportStyles(): Promise<string> {
  const imports: string[] = [];
  const rules: string[] = [];
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      rules.push(Array.from(sheet.cssRules, (rule) => rule.cssText).join("\n"));
    } catch (error) {
      if (!sheet.href) throw error;
      const href = new URL(sheet.href, location.href).href;
      imports.push(`@import url(${JSON.stringify(href)});`);
    }
  }
  // CSS @import rules must precede ordinary rules to take effect.
  return [...imports, ...rules].join("\n");
}

function waitForImage(image: HTMLImageElement): Promise<void> {
  if (image.complete) return Promise.resolve();
  return new Promise((resolve) => {
    const finish = () => {
      window.clearTimeout(timeout);
      image.removeEventListener("load", finish);
      image.removeEventListener("error", finish);
      resolve();
    };
    const timeout = window.setTimeout(finish, 3000);
    image.addEventListener("load", finish, { once: true });
    image.addEventListener("error", finish, { once: true });
    // Hidden frames must also load images that were marked lazy in the report.
    image.loading = "eager";
    if (image.complete) finish();
  });
}

async function printReportDocument(html: string): Promise<void> {
  const iframe = document.createElement("iframe");
  iframe.title = "报告打印文档";
  iframe.setAttribute("aria-hidden", "true");
  iframe.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  let removed = false;
  let cleanupTimer: number | undefined;
  let finishPrint: (() => void) | undefined;
  const cleanup = () => {
    if (removed) return;
    removed = true;
    window.clearTimeout(cleanupTimer);
    iframe.contentWindow?.removeEventListener("afterprint", cleanup);
    iframe.remove();
    finishPrint?.();
  };
  try {
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        iframe.removeEventListener("load", loaded);
        reject(new Error("报告打印文档加载超时"));
      }, 15000);
      const loaded = () => {
        window.clearTimeout(timeout);
        resolve();
      };
      iframe.addEventListener("load", loaded, { once: true });
      iframe.srcdoc = html;
      document.body.appendChild(iframe);
    });
    const frameDocument = iframe.contentDocument;
    const frameWindow = iframe.contentWindow;
    if (!frameDocument || !frameWindow) throw new Error("无法访问报告打印文档");
    if (frameDocument.fonts) {
      // A broken remote font must not leave the print button waiting forever.
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(resolve, 3000);
        frameDocument.fonts.ready.then(() => {
          window.clearTimeout(timeout);
          resolve();
        }, (error) => {
          window.clearTimeout(timeout);
          reject(error);
        });
      });
    }
    await Promise.all(Array.from(frameDocument.images, waitForImage));
    await new Promise<void>((resolve) => {
      finishPrint = resolve;
      frameWindow.addEventListener("afterprint", cleanup, { once: true });
      cleanupTimer = window.setTimeout(cleanup, 60000);
      frameWindow.focus();
      frameWindow.print();
    });
  } finally {
    cleanup();
  }
}

export function ReportDialog({ open, onClose, text, sources, title }: {
  open: boolean;
  onClose: () => void;
  text: string;
  sources?: AgentSource[];
  title?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [printing, setPrinting] = useState(false);
  const printingRef = useRef(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const createReportDocument = useCallback(async () => {
    const node = document.getElementById("report-dialog-body");
    if (!node) throw new Error("未找到报告正文");
    return buildReportDocument({
      title: title ?? "研究报告",
      bodyHtml: node.innerHTML,
      cssText: await collectReportStyles(),
      themeAttr: document.documentElement.dataset.theme,
    });
  }, [title]);

  /** 导出与打印共用独立文档，下载文件包含完整正文与内联样式。 */
  const exportHtml = useCallback(async () => {
    try {
      const html = await createReportDocument();
      const blob = new Blob([html], { type: "text/html;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = reportFileName(title, "html");
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      console.error("报告 HTML 导出失败", error);
    }
  }, [createReportDocument, title]);

  const printReport = useCallback(async () => {
    if (printingRef.current) return;
    printingRef.current = true;
    setPrinting(true);
    try {
      await printReportDocument(await createReportDocument());
    } catch (error) {
      console.error("报告独立文档打印失败，退回页面打印", error);
      window.print();
    } finally {
      printingRef.current = false;
      setPrinting(false);
    }
  }, [createReportDocument]);

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
        <button type="button" onClick={printReport} disabled={printing}
          className="flex shrink-0 cursor-pointer items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-[12px] text-ink-2 transition-colors hover:border-primary/40 hover:text-primary">
          <Printer className="size-3.5" strokeWidth={2} aria-hidden /> {printing ? "准备中…" : "打印 / PDF"}
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
