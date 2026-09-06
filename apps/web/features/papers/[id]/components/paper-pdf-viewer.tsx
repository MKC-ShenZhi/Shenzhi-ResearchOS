"use client";

import { useState } from "react";
import { ExternalLink, FileText } from "lucide-react";
import { paperExternalUrl } from "@/lib/navigation/paper";

export function PaperPdfViewer({ pdfUrl, title }: { pdfUrl: string | null; title: string }) {
  const [failed, setFailed] = useState(false);
  const url = paperExternalUrl(pdfUrl);
  if (!url) return (
    <div className="flex min-h-96 h-full flex-col items-center justify-center gap-3 rounded-xl border border-line bg-card text-center text-sm text-muted">
      <FileText className="size-8 text-faint" />
      <p>当前论文暂无可用 PDF 链接</p>
      <p className="px-5 text-xs">可继续阅读摘要与元信息，或通过 DOI 访问论文主页。</p>
    </div>
  );
  return (
    <section aria-label="PDF 阅读区" className="flex h-[75dvh] min-h-96 flex-col overflow-hidden rounded-xl border border-line bg-card lg:h-full">
      <div className="shrink-0 border-b border-line p-3 text-xs text-muted">
        <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary">
          在新窗口打开 PDF <ExternalLink className="size-3" />
        </a>
        <p className="mt-1">若下方未显示 PDF，可能是来源网站限制内嵌或浏览器不支持，请使用上方链接。</p>
      </div>
      {failed ? <p role="status" className="p-8 text-sm text-muted">PDF 无法内嵌，请在新窗口打开。</p> : (
        <iframe src={url} title={`${title} — PDF`} onError={() => setFailed(true)} className="min-h-0 w-full flex-1 border-0" referrerPolicy="no-referrer" />
      )}
    </section>
  );
}
