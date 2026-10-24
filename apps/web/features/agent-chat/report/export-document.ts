function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]!);
}

/** Build the same standalone, expanded document for printing and HTML download. */
export function buildReportDocument(input: {
  title: string;
  bodyHtml: string;
  cssText: string;
  themeAttr?: string;
}): string {
  const theme = input.themeAttr === undefined ? "" : ` data-theme="${escapeHtml(input.themeAttr)}"`;
  return `<!doctype html>
<html lang="zh-CN"${theme}>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(input.title)}</title>
<style>${input.cssText}</style>
<style>
html, body { height: auto !important; overflow: visible !important; background: #fff !important; }
body { max-width: 820px; margin: 32px auto; padding: 0 20px;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
#report-export-root * { max-height: none !important; }
#report-export-root .overflow-y-auto, #report-export-root .overflow-x-auto,
#report-export-root .overflow-auto { overflow: visible !important; }
#report-export-root .truncate { white-space: normal !important; overflow: visible !important;
                                text-overflow: clip !important; }
#report-export-root .sticky { position: static !important; }
[data-print-hide] { display: none !important; }
[data-print-only] { display: block !important; }
#report-export-root table { width: 100% !important; table-layout: auto; word-break: break-word; }
#report-export-root th, #report-export-root td { min-width: 0 !important; }
#report-export-root pre { white-space: pre-wrap !important; word-break: break-word; }
#report-export-root img { max-width: 100% !important; height: auto !important; }
h1, h2, h3, h4 { break-after: avoid; page-break-after: avoid; }
tr, img, pre, blockquote, figure { break-inside: avoid; page-break-inside: avoid; }
@page { size: A4; margin: 16mm 14mm; }
@media print { body { margin: 0 auto; } }
</style></head>
<body><div id="report-export-root">${input.bodyHtml}</div></body></html>`;
}

export function reportFileName(title: string | undefined, ext: string): string {
  return `${(title || "report").replace(/[\\/:*?"<>|]/g, "_").slice(0, 60)}.${ext}`;
}
